import socket
import select
import time
import traceback
import colorama
from colorama import Fore, Style
import threading
from threading import Thread
import requests

# Always initialize colorama
colorama.init()

### Utility functions go here :)
def parse_tags(tags):
    tag_dict = {}
    for tag_pair in tags.split(";"):
        tag,content = tag_pair.split("=")
        tag_dict[tag] = content
    return tag_dict

def encodeb(message):
    return bytes(message, 'utf-8')

class GetterRay(Thread):
    def __init__(self, user, oauth, channel, verbose=False):
        Thread.__init__(self)
        self.user = user
        self.oauth = oauth
        self.channel = channel
        self.is_mod = False
        self.msg_q = []
        self.timestamps = []
        self.last_sent = time.time() - 10
        self.verbose = verbose
        self.condition = threading.Condition()
        self.socket = socket.socket()
        self.recv_timeout = 5 # timeout in seconds to receive data
        self.connect()

    def connect(self):
        self.socket.connect(('irc.chat.twitch.tv', 6667)) # connect to Twitch
        self.send_data('PASS ' + self.oauth, silent=False)
        self.send_data('NICK ' + self.user, silent=False)
        self.recv()
        self.send_data('JOIN ' + self.channel, silent=False)
        self.recv()
        self.send_data('CAP REQ :twitch.tv/membership', silent=False)
        self.send_data('CAP REQ :twitch.tv/tags', silent=False)
        self.send_data('CAP REQ :twitch.tv/commands', silent=False)
        self.recv()

    def recv(self):
        print("B.A")
        ready = select.select([self.socket], [], [], self.recv_timeout)
        if ready[0]:
            data = self.socket.recv(2048).decode('utf-8', 'ignore')
            print("B.B")
            if data.strip():
                messages = data.split('\r\n')
                forwarded = [] # strip out administrative messages
                for message in messages:
                    if message.strip() == "PING :tmi.twitch.tv":
                        self.pong()
                    elif "USERSTATE" in message:
                        self.check_mod(message)
                    else:
                        forwarded.append(message)
                return forwarded
        else:
            print("B.C")
            return []

    def pong(self):
        self.send_data("PONG :tmi.twitch.tv", silent=True)

    def check_mod(self, data):
        chunks = data.split(" ")
        try:
            tags = parse_tags(chunks[0])
        except Exception:
            print(traceback.format_exc())
            print(f'{Fore.MAGENTA}' + data + f'{Style.RESET_ALL}')
            return {}
        if tags["mod"] == "1":
            self.is_mod = True
        else:
            self.is_mod = False

    def get_rate_limit(self):
        if self.is_mod:
            return 0.1
        else:
            return 1.1

    def get_msg_limit(self):
        if self.is_mod:
            return 100
        else:
            return 20

    def queue_data(self, message):
        self.msg_q.append(message)

    def send_queued_data(self, silent=False):
        if len(self.timestamps) > 0:
            while self.timestamps[0] - time.time() > 30:
                self.timestamps.pop()
        while len(self.msg_q) > 0:
            if len(self.timestamps) < self.get_msg_limit():
                time_since_last = time.time() - self.last_sent
                if time_since_last < self.get_rate_limit():
                    time.sleep(self.get_rate_limit() - time_since_last)
                self.send_data(self.msg_q[0], silent)
                self.timestamps.append(time.time())
                self.last_sent = time.time()
                self.msg_q = self.msg_q[1:]
            else:
                break

    def send_data(self, message, silent=False):
        self.socket.send(encodeb(message + '\r\n'))
        if not silent and self.verbose:
            print(f'{Fore.YELLOW}SENT: ' + message + f'{Style.RESET_ALL}')

    def run(self):
        self.condition.acquire()
        while True:
            self.send_queued_data()
            self.condition.wait()
        self.condition.release()

class GetterCore:
    def __init__(self, user, oauth):
        self.user = user
        self.oauth = oauth
        self.workers = {}
        self.last_time = time.time()

    def join(self, channel, verbose=False):
        self.workers[channel] = GetterRay(self.user, self.oauth, channel,
        verbose=verbose)
        self.workers[channel].start()

    def listen(self):
        for channel in self.workers:
            worker_listener = Thread(target = self.listen_to_worker,
            args = (channel,))
            worker_listener.start()

    def listen_to_worker(self, channel):
        worker = self.workers[channel]
        while True:
            print("A")
            try:
                print("B")
                messages = worker.recv()
                print("C")
                if messages:
                    messages = list(filter(lambda x: len(x) > 0, messages))
                    map(str.strip, messages)
                    print(f'{Fore.GREEN}RECV: ' + '\r\n'.join(messages) + 
                    f'{Style.RESET_ALL}')
                    thread = Thread(target = self.parse_message,
                    args = (messages, ))
                    thread.start()
                else:
                    continue
            except Exception:
                print(f'{Fore.RED}Something went wrong: ' +
                traceback.format_exc() + f'{Style.RESET_ALL}')

    def parse_message(self, messages):
        for message in messages:
            if "PRIVMSG" in message:
                parse = message.split(";")
                usertype = parse[-1]
                username = usertype.split(":")[1].split("!")[0]
                core_message = usertype[usertype.find("twitch.tv") + 
                len("twitch.tv "):] # get everything after the userstring
                user_message = ":".join(core_message.split(":")[1:])
                channel = core_message.split(" ")[1]

                if self.user.lower() in user_message.lower():
                    self.on_mention(user_message, username, channel)
                elif user_message.startswith("!"):
                    self.run_command(user_message, username, channel)
                else:
                    self.handle_message(user_message, username, channel)
    
    def on_mention(self, user_message, username, channel):
        print(f'{Fore.RED}Function needs to be implemented!{Style.RESET_ALL}')

    def run_command(self, user_message, username, channel):
        print(f'{Fore.RED}Function needs to be implemented!{Style.RESET_ALL}')

    def handle_message(self, user_message, username, channel):
        print(f'{Fore.RED}Function needs to be implemented!{Style.RESET_ALL}')

    def send_msg(self, message, channel):
        self.workers[channel].condition.acquire()
        self.workers[channel].queue_data('PRIVMSG ' + channel + " :" + message)
        self.workers[channel].condition.notify()
        self.workers[channel].condition.release()

    def fetch_url(self, url):
        response = requests.get(url)
        return response.text
    