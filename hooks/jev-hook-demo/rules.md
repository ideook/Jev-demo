# Access policy for the synthetic Jev hook demo

- [AUTH-001] An authenticated admin can read a record owned by another user.
- [AUTH-002] An authenticated employee can read their own record.
- [AUTH-003] An authenticated employee must be denied access to another user's record.
- [AUTH-004] An unauthenticated user must be denied access, including to their own record.

Each rule needs a test that calls the access function and asserts the stated result.
These are synthetic examples and contain no company data.
