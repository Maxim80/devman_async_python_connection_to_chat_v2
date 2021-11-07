from tkinter import messagebox
import tkinter as tk
import asyncio
import aiofiles
import json


HOST = 'minechat.dvmn.org'
PORT = 5050


async def register():
    nickname = entry.get()
    entry.delete(0, tk.END)
    try:
        reader, writer = await asyncio.open_connection(HOST, PORT)

        await reader.readline()

        writer.write('\n'.encode())
        await writer.drain()

        await reader.readline()

        writer.write(f'{nickname}\n'.encode())
        await writer.drain()

        response = await reader.readline()
        response = response.decode()
        access_token = json.loads(response)['account_hash']

        async with aiofiles.open('.env', 'w') as f:
            await f.write(f'MINECHAT_ACCESS_TOKEN = "{access_token}"')

        messagebox.showinfo('', f'Пользователь {nickname} успешно зарегистрирован')
        root.destroy()


    finally:
        writer.close()
        await writer.wait_closed()


def wrapper():
    asyncio.run(register())


if __name__ == '__main__':
    label_text = """
    Для отправки сообщения в чат необходимо зарегистрироваться.
    Введите желаемое имя пользователя и нажмите 'Зарегистрировать пользователя'
    """

    root = tk.Tk()
    root.title('Minechat')

    label = tk.Label(text=label_text)
    label.pack()

    entry = tk.Entry(width=50)
    entry.pack()

    button = tk.Button(text='Зарегистрировать пользователя')
    button.config(command=wrapper)
    button.pack()

    root.mainloop()
