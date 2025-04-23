-- SQL script to manually add a PRO subscription and payment item based on user id.
-- Handles existing subscriptions based on v_mode ('default', 'cancel_existing', 'replace_all').
-- Pauses active FREE subscription upon successful PRO creation, or creates a new paused FREE sub if none exists.
-- NOTE: Replace <user_id> and set v_mode as needed.

DO $$
DECLARE
    -- Input Parameters
    v_user_id UUID := '<user_id>'; -- <<< SET USER ID HERE
    v_mode TEXT := 'default'; -- <<< SET MODE HERE ('default', 'cancel_existing', 'replace_all')

    -- Variables
    v_virtual_lab_id UUID;
    v_pro_tier_id UUID;
    v_free_tier_id UUID; -- For creating paused free sub
    v_subscription_id UUID := gen_random_uuid();
    v_payment_id UUID := gen_random_uuid();
    v_paused_free_sub_id UUID := gen_random_uuid(); -- For new paused free sub
    v_now TIMESTAMPTZ := NOW();
    v_period_end TIMESTAMPTZ := v_now + INTERVAL '1 year';
    v_far_future TIMESTAMPTZ := v_now + INTERVAL '100 years'; -- For free sub end date
    v_stripe_sub_id TEXT := 'sub_manual_' || replace(gen_random_uuid()::text, '-', '');
    v_stripe_price_id TEXT;
    v_stripe_customer_id TEXT := 'cus_manual_' || replace(v_user_id::text, '-', '');
    v_stripe_invoice_id TEXT := 'in_manual_' || replace(gen_random_uuid()::text, '-', '');
    v_stripe_pi_id TEXT := 'pi_manual_' || replace(gen_random_uuid()::text, '-', '');
    v_stripe_charge_id TEXT := 'ch_manual_' || replace(gen_random_uuid()::text, '-', '');
    v_pro_yearly_amount INT;
    v_pro_currency TEXT;
    v_pro_subscription_type TEXT;
    v_existing_active_paid_sub_id UUID;
    v_existing_free_sub_id UUID;
    v_existing_free_sub_status TEXT;
    v_all_paid_sub_ids UUID[];
    v_deleted_count INT;
    v_updated_count INT;

BEGIN
    RAISE NOTICE 'Processing User ID: %, Mode: %', v_user_id, v_mode;

    -- Validate mode
    IF v_mode NOT IN ('default', 'cancel_existing', 'replace_all') THEN
        RAISE EXCEPTION 'Invalid mode specified: %. Use ''default'', ''cancel_existing'', or ''replace_all''.', v_mode;
    END IF;

    -- --- Find Virtual Lab (unchanged) ---
    SELECT id INTO v_virtual_lab_id
    FROM virtual_lab
    WHERE owner_id = v_user_id::uuid AND deleted = FALSE
    LIMIT 1;
    -- ... (RAISE NOTICE for lab found/not found remains the same) ...
    IF v_virtual_lab_id IS NOT NULL THEN
        RAISE NOTICE 'Found active Virtual Lab % owned by User %.', v_virtual_lab_id, v_user_id;
    ELSE
        RAISE NOTICE 'Notice: No active Virtual Lab found for User ID %. Proceeding without lab association.', v_user_id;
    END IF;


    -- --- Find PRO Tier (unchanged) ---
    SELECT id, yearly_amount, currency, stripe_yearly_price_id, tier::text
    INTO v_pro_tier_id, v_pro_yearly_amount, v_pro_currency, v_stripe_price_id, v_pro_subscription_type
    FROM subscription_tier
    WHERE tier = 'PRO' AND active = TRUE;
    -- ... (Error handling for tier not found or missing price ID remains the same) ...
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Error: Active PRO subscription tier not found in the database. Ensure it exists and is active.';
    END IF;
    IF v_stripe_price_id IS NULL THEN
       RAISE EXCEPTION 'Error: Active PRO subscription tier (ID %) found, but it does not have a stripe_yearly_price_id defined. Please update the tier.', v_pro_tier_id;
    END IF;


    -- --- Handle Existing Paid Subscriptions based on mode ---
    IF v_mode = 'cancel_existing' OR v_mode = 'default' THEN
        -- Find currently *active* paid subscription
        SELECT id INTO v_existing_active_paid_sub_id
        FROM subscription
        WHERE user_id = v_user_id AND status = 'ACTIVE' AND type = 'paid'
        LIMIT 1; -- Assuming only one can be active

        IF v_existing_active_paid_sub_id IS NOT NULL THEN
            IF v_mode = 'default' THEN
                RAISE EXCEPTION 'An active paid subscription (ID %) already exists for User %. Use mode ''cancel_existing'' or ''replace_all'' to override.', v_existing_active_paid_sub_id, v_user_id;
            ELSIF v_mode = 'cancel_existing' THEN
                RAISE NOTICE 'Found active paid subscription %. Setting status to CANCELED.', v_existing_active_paid_sub_id;
                UPDATE subscription
                SET status = 'CANCELED', updated_at = v_now
                WHERE id = v_existing_active_paid_sub_id;
                GET DIAGNOSTICS v_updated_count = ROW_COUNT;
                RAISE NOTICE 'Updated % subscription record to CANCELED.', v_updated_count;
            END IF;
        ELSE
             RAISE NOTICE 'No active paid subscription found for User %. Proceeding.', v_user_id;
        END IF;

    ELSIF v_mode = 'replace_all' THEN
        RAISE NOTICE 'Mode ''replace_all'': Deleting all previous paid subscriptions for User %.', v_user_id;
        -- Find *all* paid subscription IDs for the user
        SELECT array_agg(id) INTO v_all_paid_sub_ids
        FROM subscription
        WHERE user_id = v_user_id AND type = 'paid';

        IF v_all_paid_sub_ids IS NOT NULL AND array_length(v_all_paid_sub_ids, 1) > 0 THEN
            RAISE NOTICE 'Found paid subscription IDs to delete: %', v_all_paid_sub_ids;

            -- Delete payments first
            DELETE FROM subscription_payment WHERE subscription_id = ANY(v_all_paid_sub_ids);
            GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
            RAISE NOTICE 'Deleted % associated payment records.', v_deleted_count;

            -- Delete paid_subscription details
            DELETE FROM paid_subscription WHERE id = ANY(v_all_paid_sub_ids);
            GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
            RAISE NOTICE 'Deleted % paid_subscription records.', v_deleted_count;

            -- Delete base subscription records
            DELETE FROM subscription WHERE id = ANY(v_all_paid_sub_ids);
            GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
            RAISE NOTICE 'Deleted % base subscription records.', v_deleted_count;
        ELSE
            RAISE NOTICE 'No previous paid subscriptions found to delete.';
        END IF;
    END IF;

    -- --- Create New PRO Subscription (Inserts remain the same) ---
    RAISE NOTICE 'Proceeding to insert new PRO subscription.';
    INSERT INTO subscription (
        id, user_id, virtual_lab_id, tier_id, subscription_type,
        current_period_start, current_period_end, status, type,
        source, created_at, updated_at
    )
    VALUES (
        v_subscription_id, v_user_id::uuid, v_virtual_lab_id, v_pro_tier_id, v_pro_subscription_type,
        v_now, v_period_end, 'ACTIVE', 'paid',
        'SQL', v_now, v_now
    );
    RAISE NOTICE 'Inserted subscription record %.', v_subscription_id;

    INSERT INTO paid_subscription (
        id, stripe_subscription_id, stripe_price_id, customer_id,
        cancel_at_period_end, auto_renew, amount, currency, interval
    )
    VALUES (
        v_subscription_id, v_stripe_sub_id, v_stripe_price_id, v_stripe_customer_id,
        FALSE, FALSE, v_pro_yearly_amount, v_pro_currency, 'year'
    );
    RAISE NOTICE 'Inserted paid_subscription details for %.', v_subscription_id;

    INSERT INTO subscription_payment (
        id, subscription_id, customer_id, virtual_lab_id,
        stripe_invoice_id, stripe_payment_intent_id, stripe_charge_id,
        card_brand, card_last4, card_exp_month, card_exp_year,
        amount_paid, currency, status,
        period_start, period_end, payment_date, standalone,
        created_at, updated_at
    )
    VALUES (
        v_payment_id, v_subscription_id, v_stripe_customer_id, v_virtual_lab_id,
        v_stripe_invoice_id, v_stripe_pi_id, v_stripe_charge_id,
        'manual', '0000', 12, EXTRACT(YEAR FROM v_now) + 3,
        v_pro_yearly_amount, v_pro_currency, 'SUCCEEDED',
        v_now, v_period_end, v_now, FALSE,
        v_now, v_now
    );
    RAISE NOTICE 'Inserted payment record %.', v_payment_id;

    -- --- Ensure FREE Subscription is PAUSED ---
    RAISE NOTICE 'Ensuring FREE subscription is paused for User %.', v_user_id;

    -- Check for existing FREE subscription
    SELECT id, status INTO v_existing_free_sub_id, v_existing_free_sub_status
    FROM subscription
    WHERE user_id = v_user_id AND subscription_type = 'FREE'
    ORDER BY created_at DESC
    LIMIT 1;

    IF v_existing_free_sub_id IS NOT NULL THEN
        -- Free subscription exists
        IF v_existing_free_sub_status = 'ACTIVE' THEN
            RAISE NOTICE 'Found active FREE subscription %. Setting status to PAUSED.', v_existing_free_sub_id;
            UPDATE subscription
            SET status = 'PAUSED', updated_at = v_now
            WHERE id = v_existing_free_sub_id;
            GET DIAGNOSTICS v_updated_count = ROW_COUNT;
            RAISE NOTICE 'Updated % FREE subscription record to PAUSED.', v_updated_count;
        ELSE
            RAISE NOTICE 'Found existing FREE subscription % with status %. No status change needed.', v_existing_free_sub_id, v_existing_free_sub_status;
        END IF;
    ELSE
        -- No FREE subscription exists, create a new one in PAUSED state
        RAISE NOTICE 'No FREE subscription found for User %. Creating a new one in PAUSED state.', v_user_id;

        -- Find the active FREE tier
        SELECT id INTO v_free_tier_id
        FROM subscription_tier
        WHERE tier = 'FREE' AND active = TRUE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Configuration Error: Active FREE subscription tier not found. Cannot create paused free subscription.';
        END IF;

        -- Insert into base subscription table
        INSERT INTO subscription (
            id, user_id, virtual_lab_id, tier_id, subscription_type,
            current_period_start, current_period_end, status, type,
            source, created_at, updated_at
        )
        VALUES (
            v_paused_free_sub_id, v_user_id, NULL, v_free_tier_id, 'FREE',
            v_now, v_far_future, 'PAUSED', 'free', -- Create as PAUSED
            'SQL', v_now, v_now
        );

        -- Insert into free_subscription table
        INSERT INTO free_subscription (
            id, usage_count
        )
        VALUES (
            v_paused_free_sub_id, 0
        );
        RAISE NOTICE 'Created new PAUSED FREE subscription (ID: %) for User %.', v_paused_free_sub_id, v_user_id;
    END IF;

    -- --- Final Success Message (unchanged) ---
    IF v_virtual_lab_id IS NOT NULL THEN
        RAISE NOTICE 'Successfully created PRO subscription % and payment % for User % in Lab %.',
                     v_subscription_id, v_payment_id, v_user_id, v_virtual_lab_id;
    ELSE
        RAISE NOTICE 'Successfully created PRO subscription % and payment % for User % (no active lab found).',
                     v_subscription_id, v_payment_id, v_user_id;
    END IF;


EXCEPTION
    WHEN OTHERS THEN
        -- Rollback is implicit in DO block on exception
        RAISE EXCEPTION 'Error occurred: %. Transaction rolled back.', SQLERRM;
END;
$$ LANGUAGE plpgsql;