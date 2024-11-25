import unittest
import asyncio
from unittest.mock import patch, MagicMock
import aiohttp

from services.selenium_service import get_bing_first_href


class TestBingSearch(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.get_event_loop()

    @patch('aiohttp.ClientSession.get')
    def test_get_bing_first_href_success(self, mock_get):
        # 创建一个模拟的HTTP响应对象
        mock_response = MagicMock()
        mock_response.status = 200

        async def mock_text():
            return '<div class="b_attribution"><cite>https://example.com</cite></div>'

        mock_response.text = mock_text
        mock_get.return_value.__aenter__.return_value = mock_response

        # 调用要测试的异步方法
        result = self.loop.run_until_complete(get_bing_first_href("测试关键词"))

        # 打印结果
        print("test_get_bing_first_href_success result:", result)

        # 验证结果是否如预期
        self.assertEqual(result, 'https://example.com')

    @patch('aiohttp.ClientSession.get')
    def test_get_bing_first_href_no_cite(self, mock_get):
        mock_response = MagicMock()
        mock_response.status = 200

        async def mock_text():
            return '<div class="b_attribution"></div>'

        mock_response.text = mock_text
        mock_get.return_value.__aenter__.return_value = mock_response

        result = self.loop.run_until_complete(get_bing_first_href("测试关键词"))

        # 打印结果
        print("test_get_bing_first_href_no_cite result:", result)

        # 验证结果是否如预期
        self.assertIsNone(result)

    @patch('aiohttp.ClientSession.get')
    def test_get_bing_first_href_request_exception(self, mock_get):
        mock_get.side_effect = aiohttp.ClientError

        result = self.loop.run_until_complete(get_bing_first_href("测试关键词"))

        # 打印结果
        print("test_get_bing_first_href_request_exception result:", result)

        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
