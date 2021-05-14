import csv
import os
from datetime import datetime, timezone
from typing import Dict

import requests


class JNCUserData:
    user_id: str
    user_name: str
    auth_token: str
    premium_credits: int
    account_type: str

    def __init__(self, user_id: str, user_name: str, auth_token: str, premium_credits: int, account_type: str):
        self.user_id = user_id
        self.user_name = user_name
        self.auth_token = auth_token
        self.premium_credits = premium_credits
        self.account_type = account_type


class JNCBook:
    book_id: str
    title: str
    title_slug: str
    volume_num: int
    series_id: str
    is_preorder: bool
    series_slug: str = None
    publish_date: datetime
    is_owned: bool
    download_link: str = None

    def __init__(self, book_id: str, title: str, title_slug: str, volume_num: int, series_id: str,
                 publish_date: str, is_preorder: bool, series_slug: str, is_owned: bool, download_link: str):
        self.publish_date = datetime.fromisoformat(publish_date.rstrip('Z')).replace(tzinfo=timezone.utc)
        self.series_id = series_id
        self.volume_num = volume_num
        self.title_slug = title_slug
        self.title = title
        self.book_id = book_id
        self.is_preorder = is_preorder
        self.series_slug = series_slug
        self.is_owned = is_owned
        self.download_link = download_link


class JNClient:
    """Everything you need to talk to the JNC API"""

    LOGIN_URL = 'https://api.j-novel.club/api/users/login?include=user'
    FETCH_LIBRARY_URL = 'https://labs.j-novel.club/app/v1/me/library?include=serie&format=json'
    BUY_CREDITS_URL = 'https://api.j-novel.club/api/users/me/purchasecredit'

    ACCOUNT_TYPE_PREMIUM = 'PremiumMembership'

    @staticmethod
    def login(user: str, password: str) -> JNCUserData:
        """
        :raise JNCApiError when the login failed
        """
        login_response = requests.post(
            JNClient.LOGIN_URL,
            headers={'Accept': 'application/json', 'content-type': 'application/json'},
            json={'email': user, 'password': password}
        ).json()

        if 'error' in login_response:
            raise JNCApiError('Login failed!')

        subscription = login_response['user']['currentSubscription']
        return JNCUserData(
            user_id=login_response['user']['id'],
            user_name=login_response['user']['name'],
            auth_token=login_response['id'],
            premium_credits=login_response['user']['earnedCredits'] - login_response['user']['usedCredits'],
            account_type=subscription['plan']['id'] if 'plan' in subscription else None
        )

    @staticmethod
    def fetch_library(auth_token: str) -> Dict[str, JNCBook]:
        response = requests.post(
            JNClient.FETCH_LIBRARY_URL,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {auth_token}'
            }
        ).json()

        if not response.status_code < 300:
            raise JNCApiError('Could not fetch library!')
        result = {}
        for item in response['books']:
            download_link = None
            for link in item['downloads']:
                download_link = link['link'] if link['type'] is 'EPUB' else None
                if download_link is not None:
                    break

            volume = item['volume']
            result[volume['legacyId']] = JNCBook(
                book_id=volume['legacyId'],
                title=volume['title'],
                title_slug=volume['slug'],
                volume_num=volume['number'],
                publish_date=volume['publishing'],
                is_preorder=True if item['status'] is 'PREORDER' else False,
                is_owned=volume['owned'],
                series_id=item.get('serie', {}).get('legacyId', None),
                series_slug=item.get('serie', {}).get('slug', None),
                download_link=download_link
            )
        return result

    @staticmethod
    def buy_credits(auth_token: str, amount: int) -> None:
        """
        Buy premium credits on JNC. Max. amount: 10. Price depends on membership status.

        :raises ArgumentError   when amount is out of range
        :raises JNCApiError     when the purchase request fails for any reason
        """
        if 0 >= amount > 10:
            raise ArgumentError('It is not possible to buy less than 1 or more than 10 credits.')

        response = requests.post(
            JNClient.BUY_CREDITS_URL,
            headers={
                'Accept': 'application/json',  # maybe */*?
                'Content-Type': 'application/json',
                'Authorization': auth_token
            },
            json={'number': amount},
            allow_redirects=False
        )

        if not response.status_code < 300:
            raise JNCApiError('Could not purchase credits!')


class JNCUtils:
    @staticmethod
    def user_confirm(message: str) -> bool:
        answer = input(message + ' (y/n)')
        return True if answer is 'y' else False

    @staticmethod
    def sort_books(books: Dict[str, JNCBook]) -> Dict[str, JNCBook]:
        """Sorts List of JNCBooks by their series slug and volume number and returns result"""
        sorted_book_ids = sorted(
            books,
            key=lambda k: (books[k].series_slug or books[k].title_slug, books[k].volume_num)
        )
        return {book_id: books[book_id] for book_id in sorted_book_ids}

    @staticmethod
    def read_downloaded_books_file(csv_path: str) -> set:
        """First column of the csv is expected to be the book id"""
        with open(csv_path, mode='r', newline='') as f:
            book_ids = set([row[0] for row in csv.reader(f, delimiter='\t')])
        return book_ids

    @staticmethod
    def download_book(target_dir: str, book: JNCBook) -> None:
        try:
            if book.download_link is None:
                raise RuntimeError('Book does not have a download link.')

            download_response = requests.get(book.download_link)

            if download_response.status_code != 200:
                raise JNCApiError(str(download_response.status_code) + ': Book not available.')

            book_file_name = book.title_slug + '.epub'
            book_file_path = os.path.join(target_dir, book_file_name)

            with open(book_file_path, mode='wb') as f:
                f.write(download_response.content)

            book.is_owned = True
        except JNCApiError as err:
            print(err)


class JNCApiError(Exception):
    pass


class NoCreditsError(Exception):
    pass


class ArgumentError(Exception):
    pass
