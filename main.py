import asyncio
import gui
import time
import argparse


async def generate_msgs(queue):
    while True:
        queue.put_nowait(f'Ping {time.time()}')
        await asyncio.sleep(0)


async def read_msgs(host, port, queue):
    try:
        reader, writer = await asyncio.open_connection(host, port)
        while True:
            msg = await reader.readline()
            queue.put_nowait(msg.decode())

    finally:
        writer.close()
        await writer.wait_closed()


async def main(host, read_port, send_port):
    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()

    await asyncio.gather(
        read_msgs(host, read_port, messages_queue),
        gui.draw(messages_queue, sending_queue, status_updates_queue)
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='minechat.dvmn.org', help='IP or URL hosts address for connection.')
    parser.add_argument('--read_port', type=int, default=5000, help='Port to read.')
    parser.add_argument('--send_port', type=int, default=5050, help='Port to send.')
    args = parser.parse_args()

    asyncio.run(main(args.host, args.read_port, args.send_port))
