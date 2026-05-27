const BACKEND_URL = 'VIRTUAL_LAB_API_URL';

function onWebinarFormSubmit(e) {
  try {
    if (!e || !e.response) {
      console.error('No form response in event');
      return;
    }
    const props = PropertiesService.getScriptProperties();
    const secret        = props.getProperty('x_webhook_signature');
    const virtualLabId  = props.getProperty('x_virtual_lab_id');
    const projectId     = props.getProperty('x_project_id');
    const userId     = props.getProperty('x_user_id');
   
    if(!secret){
      console.error('Missing Script Properties: WEBHOOK_SECRET');
      return;
    }
    if(!virtualLabId){
      console.error('Missing Script Properties: VIRTUAL_LAB_ID');
      return;
    }
    if(!projectId){
      console.error('Missing Script Properties: PROJECT_ID');
      return;
    }
    if(!userId){
      console.error('Missing Script Properties: USER_ID');
      return;
    }

    const itemResponses = e.response.getItemResponses();
    const answers = {};
    itemResponses.forEach(ir => {
      answers[ir.getItem().getTitle()] = ir.getResponse();
    });

    const fullName = (answers['Name']  || '').toString().trim();
    const email    = (answers['Email'] || '').toString().trim();

    if (!email) {
      console.error('No email in submission');
      return;
    }


    const payload = {
      name: fullName,
      email: email,
      source: 'webinar_form',
      submittedAt: new Date().toISOString(),
      responseId: e.response ? e.response.getId() : Utilities.getUuid(),
    };

    const body = JSON.stringify(payload);

    // HMAC-SHA256 over the raw body — IDs are inside, so they're signed too.
    const signature = Utilities.computeHmacSha256Signature(body, secret)
      .map(b => ('0' + (b & 0xff).toString(16)).slice(-2))
      .join('');

    const response = UrlFetchApp.fetch(`${BACKEND_URL}/invites/webhook`, {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'x-webhook-signature': signature,
        'x-virtual-lab-id': virtualLabId,
        'x-project-id': projectId,
        'x-user-id': userId,
      },
      payload: body,
      muteHttpExceptions: true,
    });

    const code = response.getResponseCode();
    if (code < 200 || code >= 300) {
      console.error('Backend error', code, response.getContentText());
    } else {
      console.log('Invite sent for', email);
    }
  } catch (err) {
    console.error('Submission handler failed:', err);
  }
}
