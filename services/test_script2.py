import unittest
import asyncio
import re

from services.selenium_service import get_first_search_result_link


# Assume get_first_search_result_link is imported from your module
# from your_module import get_first_search_result_link

class TestSearchResultLink(unittest.TestCase):

    def setUp(self):
        # Set up any necessary state before each test
        self.loop = asyncio.get_event_loop()

    def tearDown(self):
        # Clean up after each test
        self.loop.close()

    def test_get_first_search_result_link(self):
        query = "大模型排行榜"

        async def run_test():
            # Call the function with a sample query
            link = await get_first_search_result_link(query)
            print(link)
            # Check that the returned link is not None
            self.assertIsNotNone(link, "The link should not be None")

            # Basic check to ensure the result is a URL
            self.assertTrue(
                re.match(r'^https?:\/\/', link),
                "The result should be a valid URL"
            )

        # Run the asynchronous test
        self.loop.run_until_complete(run_test())


if __name__ == "__main__":
    unittest.main()
