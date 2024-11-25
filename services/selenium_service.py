from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

import aiohttp
from bs4 import BeautifulSoup
import logging

def setup_chrome_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    # 使用 WebDriver Manager 自动处理 ChromeDriver
    service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


async def get_first_search_result_link(query):
    """

    :param query:
    :return:
    """
    driver = setup_chrome_driver()

    try:
        # 访问 Bing 主页
        driver.get("https://www.bing.com/?mkt=zh-CN")

        # 找到搜索框并输入查询
        search_box = driver.find_element(By.NAME, "q")
        search_box.send_keys(query)
        search_box.submit()

        # 等待搜索结果出现
        wait = WebDriverWait(driver, 10)
        first_result = wait.until(EC.presence_of_element_located((By.XPATH, '//li[@class="b_algo"]/h2/a')))

        # 获取第一个结果的链接
        first_link = first_result.get_attribute("href")
        return first_link

    finally:
        # 关闭浏览器
        driver.quit()


async def get_bing_first_href(keyword):
    """
    获取搜索引擎 <div class="b_attribution"> 标签下的第一个 <cite> 标签中的内容
    """
    try:
        url = f"https://www.bing.com/search?q={keyword}&mkt=zh-CN"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                html = await response.text()

        soup = BeautifulSoup(html, "html.parser")

        # 查找 <cite> 标签
        b_attribution_div = soup.find("div", class_="b_attribution")
        if b_attribution_div:
            first_cite = b_attribution_div.find("cite")
            if first_cite:
                logging.info(f"search results: {first_cite.text}")
                return first_cite.text.strip()

        return None

    except aiohttp.ClientError as e:
        logging.error(f"An error occurred: {e}")
        return None
