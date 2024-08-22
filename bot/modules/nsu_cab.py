import aiohttp
from bs4 import BeautifulSoup as BS
from random_header_generator import HeaderGenerator

from utils import delete_spaces

from .types import *
from config import cfg

NSU_ENDPOINT = 'https://cab.nsu.ru'
class WrongCookieException(Exception): pass
class LoginFailedException(Exception): pass
class ForbidenException(Exception): pass

header_generator = HeaderGenerator(user_agents = 'scrape')

class Student:
    '''Класс для доступа к апи cab.nsu.ru'''
    def __init__(self, cookie:str, session:aiohttp.ClientSession=None):
        """Создаёт экземпляр апи, привязаный к купи

        Args:
            cookie (str): куки, полученый в `get_cookie`
            session (aiohttp.ClientSession, optional): Сессия для batched запросов, чтобы не сбрасывать подключение. Defaults to None.
        """
        self.cookie = cookie
        self.session = session or aiohttp.ClientSession(NSU_ENDPOINT, headers={**header_generator(country='ru'),'Cookie': cookie}) # 
    
    async def get_profile(self) -> Profile:
        '''Получить свой профиль'''
        async with self.session.get('/user/profile', headers={'Cookie': self.cookie}) as r:
            if len(r.history) != 0: raise WrongCookieException('Invalid cookie')
            
            profile = BS(await r.text(), 'html.parser').find('div', class_='row featurette')
            return Profile(
                name = profile.find('p', class_='name').text.strip(),
                group = profile.find('b', text='Группа:').next_sibling.strip(),
                image = NSU_ENDPOINT + profile.find('img')['src']
            )
    
    async def latest_marks(self) -> list[Subject]:
        '''Получить список предметов с последними 5ю оценками'''
        async with self.session.get('/vkistudent/journal', headers={'Cookie': self.cookie}) as r:
            if len(r.history) != 0: raise WrongCookieException('Invalid cookie')
            if r.status == 403: raise ForbidenException('Forbiden')
            
            last_tab = BS(await r.text(), 'html.parser').find_all(class_='tab-pane')[-1]
            subjects = []
            for i in last_tab.find_all(class_='item-grade'):
                subjects.append(
                    Subject(
                        name = i.find(class_='name').text.strip(), 
                        link = i['href'].split('?')[0], 
                        marks = [Mark(None,None,None, i.text, None) for i in i.find_all(class_='badge')]
                    ))
            return subjects

        
    async def subject_detail(self, link) -> Subject:
        """Получить все оценки по предмету

        Args:
            link (str): Ссылка, полученая в `latest_marks`
        """
        async with self.session.get(link, headers={'Cookie': self.cookie}) as r:
            if len(r.history) != 0: raise WrongCookieException('Invalid cookie')
            if r.status == 403: raise ForbidenException('Forbiden')
            
            soup = BS(await r.text(), 'html.parser')
            
            s = Subject(soup.find('li', class_='breadcrumb-item active').text.split(',', 1)[-1].strip(), [], link)
            for row in soup.find('table', class_='table-diary').find_all('tr'):
                cells = row.find_all('td')                
                if len(cells) == 7:
                    m = Mark(date = cells[0].text.strip(),
                             type = cells[1].text.strip(),
                             is_absent = cells[2].text.strip() == 'Н',
                             mark = cells[3].text.strip(),
                             theme = cells[4].text.strip())
                    if m.is_absent or m.mark:
                        s.marks.append(m)
            return s
    
    async def orders(self) -> list[Order]:
        '''Получить свои приказы'''
        async with self.session.get('/vkistudent/orders', headers={'Cookie': self.cookie}) as r:
            if len(r.history) != 0: raise WrongCookieException('Invalid cookie')
            if r.status == 403: raise ForbidenException('Forbiden')
            
            orders = []
            for row in BS(await r.text(), 'html.parser').find('table', class_='table-nsu').find_all('tr'):
                cells = row.find_all('td')
                if len(cells) == 2:
                    orders.append(Order(
                        title = cells[1].find('b').text.strip(), 
                        body = delete_spaces(cells[1].contents[-1].replace('\n', ' '))
                    ))
            return orders
    
    async def close(self):
        '''Завершить сессию '''
        await self.session.close()
        return self.cookie
    
    @classmethod
    async def auth(cls, username, password) -> 'Student':
        '''Войти в аккаунт по логину и паролю'''
        async with aiohttp.ClientSession(headers={**header_generator(country='ru')}) as session:
            async with session.post(NSU_ENDPOINT+'/user/sign-in/auth?authclient=nsu') as r:
                url = BS(await r.text(), 'html.parser').find('form', {'id': 'kc-form-login'}).get('action')
            
            async with session.post(url, data={'username': username, 'password': password}) as r:
                if 'Invalid username or password' in await r.text():
                    raise LoginFailedException('Invalid username or password')
                if not r.headers.get('Set-Cookie') or not r.headers.get('Set-Cookie').startswith('PHPSESSID'): 
                    raise LoginFailedException('Cookie not found')
                return cls(r.headers['Set-Cookie'].split(';')[0])