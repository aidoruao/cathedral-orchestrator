#!/usr/bin/env python3
"""Smoke test for Cathedral Orchestrator modules."""
import sys
sys.path.insert(0, '/home/idor/cathedral')

# Test 1: file_protocol
from file_protocol import write_file, read_file, encode_content, decode_content

result = write_file('/home/idor/cathedral/smoke_test_output.txt', 'Hello Cathedral v1.0\nLine 2')
assert result['success'], f"Write failed: {result}"
assert result['size_bytes'] > 0
print(f"PASS file_protocol.write: md5={result['md5']}")

result = read_file('/home/idor/cathedral/smoke_test_output.txt')
assert result['success'], f"Read failed: {result}"
assert 'Hello Cathedral' in result['content']
print(f"PASS file_protocol.read: {len(result['content'])} chars")

# Test base64 roundtrip
original = "test $PATH ${HOME} # comment\nnewline"
encoded = encode_content(original)
decoded = decode_content(encoded)
assert original == decoded
print(f"PASS base64 roundtrip: {len(original)} chars -> {len(encoded)} b64")

# Test 2: audit_logger
from audit_logger import log, read_log, verify_integrity

entry = log('smoke_test', 'system', {'module': 'file_protocol', 'status': 'ok'})
assert 'hash' in entry
print(f"PASS audit_logger.log: hash={entry['hash']}")

result = read_log(max_entries=5)
assert result['success']
print(f"PASS audit_logger.read: {result['total_entries']} entries")

integ = verify_integrity()
assert integ['success']
assert integ['tampered'] == 0
print(f"PASS audit_logger.verify: {integ['verified']}/{integ['total']} verified")

# Test 3: state_bridge
from state_bridge import StateBridge
sb = StateBridge()
sb.set('test.status', 'passing', actor='system', reason='Smoke test')
assert sb.get('test.status') == 'passing'
history = sb.history('test.status')
assert len(history) >= 1
print(f"PASS state_bridge: get={sb.get('test.status')}, history={len(history)} entries")

# Test 4: domain_router
from domain_router import DomainRouter
router = DomainRouter()

domains = router.detect_domains("Calculate the Helmholtz energy for R134a")
assert 'physics' in domains, f"Expected physics, got {domains}"
print(f"PASS domain_router.physics: {domains}")

domains = router.detect_domains("Write a Python function to parse JSON")
assert 'code' in domains
print(f"PASS domain_router.code: {domains}")

domains = router.detect_domains("Create a Godot shader for PBR materials")
assert 'graphics' in domains or 'code' in domains
print(f"PASS domain_router.graphics: {domains}")

# Test 5: context_engine
from context_engine import ContextEngine

covenant_path = '/home/idor/cathedral/COVENANT.json'
covenant = ContextEngine.load_covenant(covenant_path)
assert covenant['project'] == 'hvac-simulation'
print(f"PASS context_engine.load_covenant: project={covenant['project']}")

prompt = ContextEngine.build_system_prompt(covenant)
assert 'Cathedral Orchestrator' in prompt
assert 'FR-SV-005' in prompt
print(f"PASS context_engine.build_system_prompt: {len(prompt)} chars")

engine = ContextEngine(max_active_tokens=120000, compression_trigger=90000)
engine.add_turn("user", "Hello, what is enthalpy?")
engine.add_turn("assistant", "Enthalpy is H = U + PV...")
usage = engine.token_usage
assert usage['active_turns'] == 2
print(f"PASS context_engine: {usage['active_turns']} turns, {usage['total_tokens']} tokens")

# Test 6: operation_runner (import only, no subprocess spawn)
from operation_runner import run_operation, check_operation, list_operations
print(f"PASS operation_runner.import")

print("\n" + "=" * 50)
print("ALL SMOKE TESTS PASSED")
print("=" * 50)
