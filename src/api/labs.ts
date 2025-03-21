/**
 * Represents the possible user roles in a virtual lab
 */
export enum UserRole {
  ADMIN = 'admin',
  MEMBER = 'member'
}

/**
 * Response type for user data with their role and invite status
 */
export interface UserWithInviteStatus {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  role: UserRole;
  inviteAccepted: boolean;
}

/**
 * Response type for virtual lab user operations
 */
export interface VirtualLabUserResponse {
  message: string;
  data: {
    user: UserWithInviteStatus;
  };
}

/**
 * Changes the role of a user in a virtual lab
 * 
 * @param virtualLabId - The UUID of the virtual lab
 * @param userId - The UUID of the user whose role needs to be changed
 * @param newRole - The new role to assign to the user (admin or member)
 * @returns Promise containing the updated user information
 * @throws Error if the request fails or if the last admin tries to become a member
 * 
 * @example
 * ```typescript
 * try {
 *   const response = await changeUserRole(
 *     "123e4567-e89b-12d3-a456-426614174000",
 *     "987fcdeb-51a2-43d7-9876-543210987654",
 *     UserRole.ADMIN
 *   );
 *   console.log(`User role changed: ${response.message}`);
 * } catch (error) {
 *   console.error('Failed to change user role:', error);
 * }
 * ```
 */
export async function changeUserRole(
  virtualLabId: string,
  userId: string,
  newRole: UserRole
): Promise<VirtualLabUserResponse> {
  const response = await fetch(
    `/virtual-labs/${virtualLabId}/users/${userId}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ new_role: newRole }),
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Failed to change user role');
  }

  return response.json();
} 