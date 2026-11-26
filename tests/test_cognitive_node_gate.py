# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_cognitive_node_gate.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A confirmation asks the cognitive node, with the robot as the subject and the proof, and is withheld unless the node allows it."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hydra_umc_vla_engine.confirmation import CognitiveNodeGate, ConfirmationError, ConfirmationPolicy, ConfirmationStore
from hydra_umc_vla_engine.confirmation_proof import check_node_url, verify_proof

KEY = b"vector-key-" + b"0123456789abcdef" * 2
NODE_TOKEN = "node-bearer-" + "x" * 8


class FakeNode:
    """A cognitive node on the loopback address: it records each question and answers what it is told to."""

    def __init__(self, decision="allow", reason="confirmed", status=200):
        self.asked = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.asked.append((self.path, self.headers.get("Authorization"), body))
                payload = json.dumps({"decision": decision, "reason": reason}).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def confirm(gate, proof_key=KEY):
    store = ConfirmationStore(ConfirmationPolicy(enabled=True), b"p" * 32, "robot-1", proof_key=proof_key, gate=gate)
    pending = store.create("f" * 64, {})["pending_id"]
    token = store.prepare(pending, "ana")["confirmationToken"]
    return store, lambda: store.confirm(pending, "ana", token)


class Gate(unittest.TestCase):
    def test_the_node_is_asked_with_the_subject_and_the_proof(self):
        with FakeNode() as node:
            _store, run = confirm(CognitiveNodeGate(node.url, NODE_TOKEN))
            approval = run()
        path, authorization, question = node.asked[0]
        self.assertEqual((path, authorization), ("/autonomy/evaluate", "Bearer " + NODE_TOKEN))
        self.assertEqual((question["source"], question["level"], question["subjectId"], question["actionId"]), ("vla-engine", "execute_with_confirmation", "robot-1", "f" * 64))
        self.assertEqual(question["confirmationProof"], approval["confirmationProof"])
        self.assertEqual(verify_proof(KEY, question["confirmationProof"], expected_action_id=question["actionId"], expected_subject_id=question["subjectId"]), (True, ""))

    def test_without_a_proof_key_the_question_carries_no_proof(self):
        with FakeNode() as node:
            _store, run = confirm(CognitiveNodeGate(node.url), proof_key=None)
            run()
        self.assertNotIn("confirmationProof", node.asked[0][2])
        self.assertIsNone(node.asked[0][1])

    def test_anything_but_allow_withholds_the_approval(self):
        for decision, status, expected in (("deny", 200, 403), ("needs_confirmation", 200, 403), ("allow", 503, 503)):
            with FakeNode(decision=decision, reason="proof_invalid", status=status) as node:
                store, run = confirm(CognitiveNodeGate(node.url))
                with self.assertRaises(ConfirmationError) as caught:
                    run()
            self.assertEqual(caught.exception.status, expected)
            self.assertEqual(store.approved, 0)
            self.assertEqual(store.list(), [])

    def test_a_node_that_does_not_answer_is_a_refusal(self):
        with FakeNode() as node:
            url = node.url
        _store, run = confirm(CognitiveNodeGate(url))
        with self.assertRaises(ConfirmationError) as caught:
            run()
        self.assertEqual(caught.exception.status, 503)

    def test_the_address_is_checked(self):
        for bad in ("", "ftp://node", "http://user:pass@node", "node:8095", "http://node/?q=1"):
            with self.assertRaises(ValueError):
                check_node_url(bad)


if __name__ == "__main__":
    unittest.main()
