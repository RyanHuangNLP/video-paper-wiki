import unittest

from subtract import subtract


class SubtractTests(unittest.TestCase):
    def test_subtract_positive_result(self):
        self.assertEqual(subtract(5, 3), 2)

    def test_subtract_negative_result(self):
        self.assertEqual(subtract(3, 5), -2)

    def test_subtract_zeros(self):
        self.assertEqual(subtract(0, 0), 0)


if __name__ == "__main__":
    unittest.main()
