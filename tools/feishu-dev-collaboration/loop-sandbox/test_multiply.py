import unittest

from multiply import multiply


class MultiplyTests(unittest.TestCase):
    def test_multiply_positive(self):
        self.assertEqual(multiply(2, 3), 6)

    def test_multiply_negative(self):
        self.assertEqual(multiply(-2, 3), -6)

    def test_multiply_zero(self):
        self.assertEqual(multiply(0, 5), 0)

    def test_multiply_decimal(self):
        self.assertEqual(multiply(1.5, 2), 3)


if __name__ == "__main__":
    unittest.main()
