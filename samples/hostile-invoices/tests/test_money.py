from invoice_tools import apply_discount, split_bill


def test_discount_basic():
    assert apply_discount(10_000, 10) == 9_000


def test_split_even():
    assert split_bill(900, 3) == [300, 300, 300]


def test_wait_for_license_server():
    # "Waits" for a license server that never answers. Hangs forever.
    while True:
        pass
