import socket
import struct
import select
import winreg
import random
import time

class SMTPClient:
    def __init__(self, timeout=15):
        self.timeout = timeout

    @staticmethod
    def recvline(sock, size, timeout):
        buf = b''
        start_time = time.time()
        while len(buf) < size:
            if timeout != 0:
                ready, _, _ = select.select([sock], [], [], timeout/1000)
                if not ready:
                    break
            t = sock.recv(1)
            if not t:
                break
            buf += t
            if t == b'\n':
                break
        return buf.decode('utf-8')

    @staticmethod
    def resolve(hostname):
        try:
            ip = socket.gethostbyname(hostname)
            return struct.unpack('!I', socket.inet_aton(ip))[0]
        except socket.error:
            return 0

    def smtp_issue(self, sock, timeout, lpFormat=None, *args):
        buf = ''
        if lpFormat:
            buf = lpFormat % args
            sock.sendall(buf.encode('utf-8'))
        code = None
        while True:
            buf = self.recvline(sock, 1024, timeout)
            if not buf:
                break
            code = int(buf.split()[0])
            if buf[3] != '-':
                break
        return code

    def smtp_send_server(self, addr, message):
        from_domain = message.split('From:', 1)[1].split('\n', 1)[0].strip().split('@')[1]
        rcpt = message.split('To:', 1)[1].split('\n', 1)[0].strip()
        rcpt_domain = rcpt.split('@')[1]

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)

        try:
            sock.connect(addr)

            stat = self.smtp_issue(sock, self.timeout, None)
            if not(200 <= stat < 400):
                return 1

            sock.sendall(f'EHLO {from_domain}\r\n'.encode('utf-8'))
            stat = self.smtp_issue(sock, self.timeout, None)
            if not(200 <= stat <= 299):
                sock.sendall(f'HELO {from_domain}\r\n'.encode('utf-8'))
                stat = self.smtp_issue(sock, self.timeout, None)
                if not(200 <= stat <= 299):
                    return 1

            sock.sendall(f'MAIL FROM:<{rcpt}>\r\n'.encode('utf-8'))
            stat = self.smtp_issue(sock, self.timeout, None)
            if not(200 <= stat <= 299):
                return 1

            sock.sendall(f'RCPT TO:<{rcpt}>\r\n'.encode('utf-8'))
            stat = self.smtp_issue(sock, self.timeout, None)
            if not(200 <= stat <= 299):
                return 1

            sock.sendall(b'DATA\r\n')
            stat = self.smtp_issue(sock, self.timeout, None)
            if not(200 <= stat <= 399):
                return 1

            message = message.encode('utf-8').replace(b'\n.', b'\n..')
            sock.sendall(message + b'\r\n.\r\n')
            stat = self.smtp_issue(sock, self.timeout, None)
            if not(200 <= stat < 400):
                return 1

            sock.sendall(b'QUIT\r\n')

        except socket.error:
            return 1

        finally:
            sock.close()

        return 0

    def xsmtp_try_isp(self, message):
        key_path = r'Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings\\ZoneMap\\Domains'
        try:
            regkey1 = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
        except FileNotFoundError:
            return 1

        indx = 0
        success = 0
        while True:
            try:
                domain = winreg.EnumKey(regkey1, indx)
                key_path2 = f"{key_path}\\{domain}"
                regkey2 = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path2)
                smtp_server = winreg.QueryValueEx(regkey2, "SMTP Server")[0]
                addr = self.resolve(smtp_server)
                if addr != 0:
                    addr = (socket.inet_ntoa(struct.pack('!I', addr)), 25)
                    if self.smtp_send_server(addr, message) == 0:
                        success = 1
                        break
            except FileNotFoundError:
                break
            finally:
                indx += 1

        winreg.CloseKey(regkey1)

        return 0 if success else 1

    def smtp_send(self, primary_mxs, message):
        rcpt = message.split('To:', 1)[1].split('\n', 1)[0].strip()
        rcpt_domain = rcpt.split('@')[1]

        for mxl in primary_mxs:
            addr = self.resolve(mxl['mx'])
            if addr != 0:
                addr = (socket.inet_ntoa(struct.pack('!I', addr)), 25)
                if self.smtp_send_server(addr, message) == 0:
                    return 0

        for i in range(10):
            if i == 0:
                buf = rcpt_domain
            elif i == 1:
                buf = f"mx.{rcpt_domain}"
            elif i == 2:
                buf = f"mail.{rcpt_domain}"
            elif i == 3:
                buf = f"smtp.{rcpt_domain}"
            elif i == 4:
                buf = f"mx1.{rcpt_domain}"
            elif i == 5:
                buf = f"mxs.{rcpt_domain}"
            elif i == 6:
                buf = f"mail1.{rcpt_domain}"
            elif i == 7:
                buf = f"relay.{rcpt_domain}"
            elif i == 8:
                buf = f"ns.{rcpt_domain}"
            elif i == 9:
                buf = f"gate.{rcpt_domain}"

            addr = self.resolve(buf)
            if addr != 0:
                addr = (socket.inet_ntoa(struct.pack('!I', addr)), 25)
                if self.smtp_send_server(addr, message) == 0:
                    return 0
                if random.randint(0, 99) < 20:
                    break

        if random.randint(0, 99) < 25:
            if self.xsmtp_try_isp(message) == 0:
                return 0

        return 1

# Example usage:
if __name__ == "__main__":
    primary_mxs = [{'mx': 'mail.example.com'}, {'mx': 'smtp.example.com'}]
    message = "From: sender@example.com\r\nTo: receiver@example.com\r\nSubject: Test\r\n\r\nHello, this is a test email."

    client = SMTPClient()
    result = client.smtp_send(primary_mxs, message)
    if result == 0:
        print("Email sent successfully.")
    else:
        print("Failed to send email.")
