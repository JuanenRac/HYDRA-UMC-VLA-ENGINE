# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_confirmation_proof.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The ConfirmationProof of the SDK: the same bytes, signed when a key is given and asked for only when switched on."""

import unittest

from hydra_umc_vla_engine.confirmation_proof import proof_identifier, sign_proof, verify_proof
from hydra_umc_vla_engine.confirmation import ConfirmationPolicy, ConfirmationStore

KEY = b"vector-key-" + b"0123456789abcdef" * 2


class Proof(unittest.TestCase):
    def test_the_proof_is_the_one_of_the_sdk(self):
        for (kind, action, subject, operator, identity), signature in (
            (("approval", "f" * 64, "robot-1", "ana", "a" * 32), "40455c91e510cecef1a7f2705b206587cb7211b464862ce8a35c1fe500048477"),
            (("voice", "turn-42", "installation", proof_identifier("ana@example.com"), "b" * 32), "6d353d430780ae4a8d56cc6e062cd934998f0813b870e69887059f49fda5a281"),
        ):
            proof = sign_proof(KEY, kind=kind, action_id=action, subject_id=subject, operator=operator, approved_at_ms=1700000000000,
                               expires_at_ms=1700000010000, approval_id=identity)
            self.assertEqual(proof["signature"], signature)
            self.assertEqual(verify_proof(KEY, proof, expected_action_id=action, expected_subject_id=subject, now_ms=1700000000500), (True, ""))
            self.assertFalse(verify_proof(KEY, proof, expected_action_id=action, expected_subject_id="robot-2", now_ms=1700000000500)[0])
            self.assertFalse(verify_proof(KEY, proof, expected_action_id=action, expected_subject_id=subject, now_ms=1700000010000)[0])
            self.assertFalse(verify_proof(b"x" * 32, proof, expected_action_id=action, expected_subject_id=subject, now_ms=1700000000500)[0])

    def test_confirm_carries_a_proof_only_with_a_key(self):
        for proof_key in (None, KEY):
            store = ConfirmationStore(ConfirmationPolicy(enabled=True), b"p" * 32, "robot-1", proof_key=proof_key)
            pending = store.create("f" * 64, {})["pending_id"]
            token = store.prepare(pending, "ana@example.com")["confirmationToken"]
            approval = store.confirm(pending, "ana@example.com", token)
            if proof_key is None:
                self.assertNotIn("confirmationProof", approval)
                continue
            proof = approval["confirmationProof"]
            self.assertEqual(verify_proof(KEY, proof, expected_action_id="f" * 64, expected_subject_id="robot-1"), (True, ""))
            self.assertEqual(proof["operator"], proof_identifier("ana@example.com"))


if __name__ == "__main__":
    unittest.main()
