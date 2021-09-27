from dotenv import load_dotenv
from tkinter import messagebox
import asyncio
import aiofiles
import gui
import time
import argparse
import logging
import os
import json


class InvalidToken(Exception):
    pass


async def generate_msgs(queue):
    while True:
        queue.put_nowait(f'Ping {time.time()}')
        await asyncio.sleep(0)


async def authorize(host, port, token):
    try:
        reader, writer = await asyncio.open_connection(host, port)
        await reader.readline()
        writer.write(f'{token}\n'.encode())
        await writer.drain()
        answer = await reader.readline()
    except:
        writer.close()
        await writer.wait_closed()

    answer = json.loads(answer.decode())
    if answer is None:
        writer.close()
        await writer.wait_closed()
        raise InvalidToken

    nickname = answer['nickname']
    logger.debug(f'Выполнена авторизация. Пользователь {nickname}')
    return reader, writer


async def read_msgs(host, port, messages_queue, save_queue):
    try:
        reader, writer = await asyncio.open_connection(host, port)
        while True:
            msg = await reader.readline()
            messages_queue.put_nowait(msg.decode())
            save_queue.put_nowait(msg.decode())

    finally:
        writer.close()
        await writer.wait_closed()


async def send_msgs(host, port, writer, queue):
    while True:
        msg = await queue.get()
        writer.write(f'{msg}\n\n'.encode())
        await writer.drain()
        logger.debug(f'Пользователь написал: {msg}')


async def save_messages(filepath, queue):
    while True:
        msg = await queue.get()
        async with aiofiles.open(filepath, 'a') as f:
            await f.write(msg)


async def loading_messages_history(filepath, queue):
    try:
        async with aiofiles.open(filepath, 'r') as f:
            msgs = await f.readlines()
    except FileNotFoundError:
        return

    if msgs:
        [queue.put_nowait(msg) for msg in msgs]


async def main(host, read_port, send_port, history_filepath, token):
    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    save_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()

    try:
        reader, writer = await authorize(host, send_port, token)
    except InvalidToken:
        messagebox.showerror('Неверный токен', 'Проверьте токен. Сервер неузнал его.')
        return

    await loading_messages_history(history_filepath, messages_queue)

    await asyncio.gather(
        read_msgs(host, read_port, messages_queue, save_queue),
        send_msgs(host, send_port, writer, sending_queue),
        save_messages(history_filepath, save_queue),
        gui.draw(messages_queue, sending_queue, status_updates_queue)
    )


if __name__ == '__main__':
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='minechat.dvmn.org', help='IP or URL hosts address for connection.')
    parser.add_argument('--read_port', type=int, default=5000, help='Port to read.')
    parser.add_argument('--send_port', type=int, default=5050, help='Port to send.')
    parser.add_argument('--token', type=str, default=os.getenv('MINECHAT_ACCESS_TOKEN'),
        help='Chat authorization token.')
    parser.add_argument('--history', type=str, default='./minechat.history',
        help='The path to the file with the message history.')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger('Log')

    asyncio.run(main(args.host, args.read_port, args.send_port, args.history, args.token))
