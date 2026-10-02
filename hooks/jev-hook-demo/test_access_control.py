"""Executable tests for the four documented access policy rules."""

import unittest

from access_control import can_read


class AccessPolicyTests(unittest.TestCase):
    def test_admin_can_read_another_users_record(self):
        self.assertTrue(can_read("admin", "admin-1", "employee-2", True))

    def test_employee_can_read_own_record(self):
        self.assertTrue(can_read("employee", "employee-1", "employee-1", True))

    def test_employee_cannot_read_another_users_record(self):
        self.assertFalse(can_read("employee", "employee-1", "employee-2", True))

    def test_unauthenticated_employee_cannot_read_own_record(self):
        self.assertFalse(can_read("employee", "employee-1", "employee-1", False))

    def test_unauthenticated_admin_cannot_read_another_users_record(self):
        self.assertFalse(can_read("admin", "admin-1", "employee-2", False))


if __name__ == "__main__":
    unittest.main()
