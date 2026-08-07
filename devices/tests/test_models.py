"""
Tests de la logique métier des modèles (nécessitent la base de données).
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from devices.models import (
    Terminal,
    BiometricUser,
    BiometricCredential,
    AttendanceLog,
)


class BiometricUserTests(TestCase):
    def setUp(self):
        self.terminal = Terminal.objects.create(sn="SN-USER-001")

    def test_get_next_enrollid_empty_terminal(self):
        self.assertEqual(BiometricUser.get_next_enrollid(self.terminal), 1)

    def test_get_next_enrollid_increments(self):
        BiometricUser.objects.create(terminal=self.terminal, enrollid=5)
        self.assertEqual(BiometricUser.get_next_enrollid(self.terminal), 6)

    def test_next_enrollid_is_terminal_scoped(self):
        other = Terminal.objects.create(sn="SN-USER-002")
        BiometricUser.objects.create(terminal=self.terminal, enrollid=9)
        # Le second terminal n'est pas impacté par le premier
        self.assertEqual(BiometricUser.get_next_enrollid(other), 1)


class CredentialPropertyTests(TestCase):
    def setUp(self):
        self.terminal = Terminal.objects.create(sn="SN-CRED-001")
        self.user = BiometricUser.objects.create(terminal=self.terminal, enrollid=1)

    def _cred(self, backupnum):
        return BiometricCredential.objects.create(
            user=self.user, backupnum=backupnum, record="x"
        )

    def test_fingerprint(self):
        self.assertTrue(self._cred(0).is_fingerprint)

    def test_password(self):
        self.assertTrue(self._cred(10).is_password)

    def test_card(self):
        self.assertTrue(self._cred(11).is_card)

    def test_face(self):
        self.assertTrue(self._cred(20).is_face)

    def test_palm(self):
        self.assertTrue(self._cred(30).is_palm)


class AttendanceInOutTests(TestCase):
    def setUp(self):
        self.terminal = Terminal.objects.create(sn="SN-ATT-001")
        self.base = timezone.now()

    def _log(self, inout, minutes_ago):
        return AttendanceLog.objects.create(
            terminal=self.terminal,
            enrollid=1,
            time=self.base - timedelta(minutes=minutes_ago),
            inout=inout,
        )

    def test_first_punch_is_entry(self):
        status = AttendanceLog.determine_inout_status(
            enrollid=1, terminal=self.terminal, current_time=self.base
        )
        self.assertEqual(status, 0)

    def test_after_entry_is_exit(self):
        self._log(inout=0, minutes_ago=10)
        status = AttendanceLog.determine_inout_status(
            enrollid=1, terminal=self.terminal, current_time=self.base
        )
        self.assertEqual(status, 1)

    def test_after_exit_is_entry(self):
        self._log(inout=0, minutes_ago=20)
        self._log(inout=1, minutes_ago=10)
        status = AttendanceLog.determine_inout_status(
            enrollid=1, terminal=self.terminal, current_time=self.base
        )
        self.assertEqual(status, 0)

    def test_get_last_attendance_returns_most_recent(self):
        self._log(inout=0, minutes_ago=30)
        recent = self._log(inout=1, minutes_ago=5)
        last = AttendanceLog.get_last_attendance(
            enrollid=1, terminal=self.terminal
        )
        self.assertEqual(last.id, recent.id)

    def test_inout_scoped_per_terminal(self):
        # Un pointage sur un autre terminal ne doit pas influencer le calcul
        other = Terminal.objects.create(sn="SN-ATT-002")
        AttendanceLog.objects.create(
            terminal=other, enrollid=1, time=self.base - timedelta(minutes=5), inout=0
        )
        status = AttendanceLog.determine_inout_status(
            enrollid=1, terminal=self.terminal, current_time=self.base
        )
        self.assertEqual(status, 0)
