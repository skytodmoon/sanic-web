import os

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import requests
from bs4 import BeautifulSoup


def setup_chrome_driver():
    """

    :return:
    """
    # 设置 Chrome 选项为无头模式
    chrome_options = Options()
    chrome_options.add_argument("--headless")

    # 获取当前脚本的绝对路径
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 获取上一级目录
    parent_dir = os.path.dirname(script_dir)

    # 创建一个服务对象，并指定 ChromeDriver 的绝对路径
    service = Service(executable_path=os.path.join(parent_dir, "chromedriver"))

    # 创建一个新的 Chrome WebDriver 实例
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
    获取搜索引擎 <div class="b_attribution"> 标签下的第一个 <cite> 标签中的内容   不稳定
    :param keyword:
    :return:
    """
    try:
        # 构建搜索URL
        url = f"https://www.bing.com/search?q={keyword}&mkt=zh-CN"

        # 设置请求头以模拟浏览器访问
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"}

        # 发送GET请求
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # 检查请求是否成功

        # 解析HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # 查找 <div class="b_attribution"> 标签
        b_attribution_div = soup.find("div", class_="b_attribution")
        if b_attribution_div:
            # 查找 <div class="b_attribution"> 下的第一个 <cite> 标签
            first_cite = b_attribution_div.find("cite")
            if first_cite:
                return first_cite.text.strip()

        return None

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None
