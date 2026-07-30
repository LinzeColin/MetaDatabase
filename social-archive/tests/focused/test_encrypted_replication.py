from pathlib import Path

from social_archive.encryption import AgeEncryptor
from social_archive.storage import ContentAddressedStore


def test_age_encryptor_reuses_exact_ciphertext(tmp_path: Path):
    source = ContentAddressedStore(tmp_path / "cas").put_bytes(b"private-object", suffix=".bin")
    calls: list[list[str]] = []

    def fake_runner(argv):
        calls.append(list(argv))
        output = Path(argv[argv.index("-o") + 1])
        input_path = Path(argv[-1])
        output.write_bytes(b"age-test-cipher:" + input_path.read_bytes())

    encryptor = AgeEncryptor(recipient="age1testrecipient", root=tmp_path / "encrypted", runner=fake_runner)
    first = encryptor.encrypt(source)
    second = encryptor.encrypt(source)

    assert len(calls) == 1
    assert first.path == second.path
    assert first.cipher_sha256 == second.cipher_sha256
    assert first.original_sha256 == source.sha256
    assert first.path.suffix == ".age"


def test_recipient_change_reencrypts_ciphertext(tmp_path: Path):
    source = ContentAddressedStore(tmp_path / "cas").put_bytes(b"private-object")
    count = 0

    def fake_runner(argv):
        nonlocal count
        count += 1
        output = Path(argv[argv.index("-o") + 1])
        output.write_bytes(f"cipher-{count}".encode())

    AgeEncryptor(recipient="age1first", root=tmp_path / "encrypted", runner=fake_runner).encrypt(source)
    result = AgeEncryptor(recipient="age1second", root=tmp_path / "encrypted", runner=fake_runner).encrypt(source)
    assert count == 2
    assert result.path.read_bytes() == b"cipher-2"
