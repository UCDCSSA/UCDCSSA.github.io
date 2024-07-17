import requests
import time
from tqdm import tqdm
import datetime
import json
import os
import os.path
from urllib.parse import unquote
from html import unescape
from unicodedata import normalize as ucnorm
from functools import partial
import re
import base64
from bs4 import BeautifulSoup

POST_DATA = dict[str, dict[str, str | int | list[dict[str, str | int]]]]

def parse_msgList(msgList_str: str) -> list:
    return eval(ucnorm("NFKD", unescape(unescape(msgList_str).replace('"', '\'\'\''))).replace('\\\\', '\\'))['list']

class API:

    def __init__(self, base_url: str, headers: dict[str, str], cookies: dict[str, str]):
        self.base_url = base_url
        self.headers = headers
        self.cookies = cookies

    def get(self, **kwargs):
        return requests.get(f"{self.base_url}?{'&'.join(f'{k}={v}' for k, v in kwargs.items())}", headers=self.headers, cookies=self.cookies)

class WeixinOfficialAccountAPI(API):

    headers = {'User-Agent': 'MicroMessenger'}

    def __init__(self, biz: str, wap_sid2: str, pass_ticket: str) -> None:
        super().__init__(
            base_url='https://mp.weixin.qq.com/mp/profile_ext', 
            headers={'User-Agent': 'MicroMessenger'}, 
            cookies={'wap_sid2': wap_sid2, 'pass_ticket': pass_ticket}
        )
        self.biz = biz

    def get(self, **kwargs):
        return super().get(__biz=self.biz, **kwargs)
    
    def home(self, **kwargs):
        res = self.get(action='home', **kwargs)
        try:
            self.cookies['appmsg_token'] = re.findall(r'appmsg_token = "(.*?)";', res.text)[0]
        except IndexError:
            print('获取 appmsg_token 失败，wap_sid2可能过期')
        return res
    
    def getmsg(self, offset=0, count=10, **kwargs):
        if 'appmsg_token' not in self.cookies or self.cookies['appmsg_token'] == '':
            raise Exception('appmsg_token 为空, 请先调用 home() 方法获取')
        return self.get(action='getmsg', offset=offset, count=count, f='json', appmsg_token=self.cookies['appmsg_token'], **kwargs)
    

class Manager:

    def __init__(self, api: WeixinOfficialAccountAPI, posts_path: str = 'data/posts.json', img_dir: str = 'imgs') -> None:
        self.api = api
        self.posts_path = posts_path
        self.img_dir = img_dir
        self.posts: list[POST_DATA] = json.load(open(posts_path, encoding='utf-8'))
        self.imgs = set(os.listdir(img_dir))

    def __download_img(self, url: str) -> None:
        filename = url.split('/')[-2] + '.jpg'
        if filename not in self.imgs:
            self.imgs.add(filename)
            return open(os.path.join(self.img_dir, filename), 'wb').write(requests.get(url).content)

    def fetch_imgs(self, posts: list[POST_DATA]) -> None:
        for post in posts:
            if 'app_msg_ext_info' in post:
                url: str = post['app_msg_ext_info']['cover']
                self.__download_img(url)
                for sub_p in post['app_msg_ext_info']['multi_app_msg_item_list']:
                    url = sub_p['cover']
                    self.__download_img(url)

    def update_posts(self, latest_posts: list[POST_DATA]) -> list[POST_DATA]:
        new_msg = []
        for p in latest_posts:
            if p['comm_msg_info']['id'] != self.posts[0]['comm_msg_info']['id']:
                new_msg.append(p)
            else:
                break
        print(f'新增{len(new_msg)}条消息')
        self.posts = new_msg + self.posts
        json.dump(self.posts, open(self.posts_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=4)
        
    def generate_readme(self) -> None:
        with open('README.md', 'w', encoding='utf-8') as f:
            f.write('# UCD学联CSAA\n')
            f.write('旨在为促进中外学生交流和为在UCD的学生提供服务的平台\n')
            with open('杂项.md', 'w', encoding='utf-8') as f2:
                f2.write('# 杂项\n')
                with open('分享图片.md', 'w', encoding='utf-8') as f3:
                    for p in self.posts:
                        timestamp = p['comm_msg_info']['datetime']
                        time = datetime.datetime.fromtimestamp(timestamp)
                        date = f'{time.year}年{time.month}月{time.day}日'
                        if 'app_msg_ext_info' in p:
                            title = p['app_msg_ext_info']['title'].replace('[', '【').replace(']', '】').replace('［', '【').replace('］', '】')
                            text = p['app_msg_ext_info']['digest']
                            url = p['app_msg_ext_info']['content_url']
                            if title == '分享图片':
                                f3.write(f'### {date}\n[{title}]({url})\n')
                            else:
                                f.write(f'### {date}\n[{title}]({url})\n')
                                for i in p['app_msg_ext_info']['multi_app_msg_item_list']:
                                    f.write(f'- [{i["title"]}]({i["content_url"]})\n')
                        else:
                            content = p["comm_msg_info"]["content"]
                            if content:
                                f2.write(f'### {date}\n{content}\n')   

    def update(self) -> None:
        latest_posts = self.get_latest_posts()
        self.fetch_imgs(latest_posts)
        self.update_posts(latest_posts)
        self.generate_readme()
        self.push_to_github()

    @staticmethod
    def push_to_github():
        os.system('git add .')
        os.system('git commit -m "syncronize"')
        os.system('git push')

    def get_latest_posts(self) -> list[POST_DATA]:
        res = self.api.home()
        msgList_str = re.findall("var msgList = '(.*?)';", res.text)
        if msgList_str == []:
            print('获取最新文章列表失败，wap_sid2可能过期')
            exit(1)
        new_posts = parse_msgList(msgList_str[0])
        return new_posts
   

if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--wap_sid2', type=str, required=True)
    parser.add_argument('--pass_ticket', type=str, required=True)

    arg = parser.parse_args()

    api = WeixinOfficialAccountAPI(
        biz='MzI0ODQ3MzUwMg==',
        wap_sid2=arg.wap_sid2,
        pass_ticket=arg.pass_ticket
    )

    manager = Manager(api)

    manager.update()
