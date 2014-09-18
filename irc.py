#!/usr/bin/python3

import os
import asyncio
import logging
import fcntl


class IRCClient(asyncio.Protocol):
    def __init__(self):
        self.buffer = ''
        self.queue = asyncio.Queue()
        self.log = logging.getLogger('irc')
        self.log.setLevel(logging.INFO)
        self.nick = 'kcr_test'
        self.username = 'kcr'
        self.name = 'Karl Ramm'
        self.done = asyncio.Future()

    def connection_made(self, transport):
        self.transport = transport
        self.command('NICK %s', self.nick)
        self.command('USER %s 0 * :%s', self.username, self.name)

    def command(self, s, *args):
        command = s % args
        self.log.debug('sent: %s', command)
        self.transport.write((command + '\r\n').encode())

    def connection_lost(self, exc):
        self.enqueue('disconnected', exc)
        self.aredone(exc)

    def data_received(self, data):
        info = data.decode()
        self.buffer += info
        while '\r\n' in self.buffer:
            line, self.buffer = self.buffer.split('\r\n', 1)
            self.line_received(line)

    def line_received(self, line):
        self.log.debug('%s', line)
        words = line.split()
        if words[1].upper() == 'MODE':
            self.command('JOIN ##kcr')
        if words[0] == 'PING':
            self.command('PONG %s' % ' '.join(words[1:]))
        self.enqueue('line', line)

    def error_received(self, exc):
        self.enqueue('error', exc)
        self.aredone(exc)

    def aredone(self, result=None):
        if not self.done.done():
            self.done.set_result(result)

    def eof_received(self):
        self.enqueue('eof', None)
        self.aredone()

    @asyncio.coroutine
    def finished(self):
        yield from self.done

    def quit(self, message='ALL DONE BYE BYE'):
        self.command('QUIT :%s', message)
        yield from self.done

    def enqueue(self, k, v):
        self.queue.put_nowait((self.transport._loop.time(), k, v))

    def new_message(self):
        result = yield from self.queue.get()
        return result


class DumbUI:
    IN = 0
    OUT = 1

    def __init__(self, loop, irc):
        self.loop = loop
        self.irc = irc
        self.buffer = ''
        self.log = logging.getLogger('DumbUI')
        self.done = asyncio.Future()

    def __enter__(self):
        ## self.inflags = fcntl.fcntl(self.IN, fcntl.F_GETFL)
        ## fcntl.fcntl(self.IN, fcntl.F_SETFL, self.inflags | os.O_NONBLOCK)
        self.loop.add_reader(self.IN, self.data_available)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        #fcntl.fcntl(self.IN, fcntl.F_SETFL, self.inflags)
        pass

    def data_available(self):
        c = os.read(self.IN, 1)
        self.buffer += c.decode()#XXX
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n')
            asyncio.async(self.line(line))

    @asyncio.coroutine
    def line(self, line):
        self.log.debug('got: %s', line)
        line = line.strip()
        if not line:
            return
        elif line.lower() == 'quit':
            yield from self.irc.quit()
            self.done.set_result(None)
        else:
            self.irc.command(line)

    def wait(self):
        yield from self.done


@asyncio.coroutine
def output_thread(irc):
    print('output thread')
    while True:
        message = yield from irc.new_message()
        print(repr(message))


@asyncio.coroutine
def do_a_thing(loop):
    transport, protocol = yield from loop.create_connection(
        IRCClient, 'irc.oftc.net', 6697, ssl=True)
    ## protocol = None

    ## yield from protocol.finished()
    logging.debug('client set up')

    output = loop.create_task(output_thread(protocol))

    with DumbUI(loop, protocol) as ui:
        yield from ui.wait()

    output.cancel()

    yield from asyncio.sleep(0)


def main():
    logging.basicConfig(level=logging.DEBUG)
    #logging.getLogger('asyncio').setLevel(logging.WARNING)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(do_a_thing(loop))


if __name__ == '__main__':
    main()
