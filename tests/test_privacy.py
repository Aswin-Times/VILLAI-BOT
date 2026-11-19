"""Phone numbers: normalise, hash for pre-consent state, mask for logs."""

from __future__ import annotations

import pytest

from app.privacy import hash_phone, mask_phone, normalise_phone


@pytest.mark.parametrize(
    "raw",
    ["whatsapp:+919876543210", "+91 98765 43210", "+91-98765-43210", "whatsapp:+91 9876543210"],
)
def test_normalises_whatsapp_and_spaced_numbers(raw: str) -> None:
    assert normalise_phone(raw) == "+919876543210"


def test_rejects_things_that_are_not_phone_numbers() -> None:
    with pytest.raises(ValueError):
        normalise_phone("whatsapp:hello")


def test_hash_is_stable_keyed_and_does_not_contain_the_number() -> None:
    h = hash_phone("+919876543210", "secret-a")

    assert h == hash_phone("+919876543210", "secret-a")
    assert h != hash_phone("+919876543210", "secret-b")
    assert "9876543210" not in h
    assert len(h) == 64


def test_mask_keeps_country_code_and_last_four() -> None:
    assert mask_phone("+919876543210") == "+91******3210"


def test_mask_never_reveals_a_short_number() -> None:
    assert "1234" not in mask_phone("+1234")
