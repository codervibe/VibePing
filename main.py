#!/usr/bin/python3
# -*- coding:utf-8 -*-

from alive_progress import alive_bar
from argparse import ArgumentParser, RawTextHelpFormatter
import json
import queue
import gevent
import threading
import re
import sys
import os
import time
from gevent import monkey
monkey.patch_all()
import requests

# global variables
task_queue = queue.Queue()
result_queue = queue.Queue()
lock = threading.Lock()


def report_result():
    dirPath = './report'
    if not os.path.exists(dirPath):
        os.mkdir(dirPath)
    cdnHost = dirPath + '/' + 'cdnHost_' + \
        time.strftime('%Y%m%d', time.localtime()) + '.txt'
    realHost = dirPath + '/' + 'realHost_' + \
        time.strftime('%Y%m%d', time.localtime()) + '.txt'
    errorHost = dirPath + '/' + 'errorHost_' + \
        time.strftime('%Y%m%d', time.localtime()) + '.txt'
    all_result = []

    # 处理输出 / Handle output
    global STOP_THIS

    try:
        while not STOP_THIS:
            if result_queue.qsize() == 0:
                time.sleep(0.1)
                continue
            while result_queue.qsize() > 0:
                all_result.append(result_queue.get())

            cdn_text = ''
            real_text = ''
            error_text = ''
            for item in all_result:
                if item['isCdn'] is True:
                    cdn_text += item['host'] + '\n'
                    cdn_text += 'ip:' + ','.join(list(item['ip'])) + '\n'
                elif item['isCdn'] is False:
                    real_text += item['host'] + '\n'
                    real_text += 'ip:' + ''.join(list(item['ip'])) + '\n'
                else:
                    error_text += item['host'] + '\n'

            with open(cdnHost, 'w') as f1, open(realHost, 'w') as f2, open(
                errorHost, 'w'
            ) as f3:
                f1.write(cdn_text)
                f2.write(real_text)
                f3.write(error_text)

        if all_result:
            print(
                '[扫描报告已保存到]:{c} {r} {e}'.format(
                    c=cdnHost, r=realHost, e=errorHost
                )
            )
        else:
            print('[错误，结果为空]')

    except Exception as e:
        print('[保存结果线程错误]: {}'.format(e))
        sys.exit(-1)


def format_producer(args):
    lines = []
    if args.host:
        lines.append(args.host.strip())

    if args.force and args.f:
        with open(args.f, 'r') as inFile:
            content = inFile.read()
        pattern = re.compile(
            r'([a-zA-Z0-9][-a-zA-Z0-9]{0,62}(\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+\.[a-z]+?)\s'
        )
        resList = pattern.findall(content)
        for h in resList:
            try:
                lines.append(list(h)[0])
            except Exception as e:
                print('[强制模式错误]:{}'.format(e))

    elif args.f:
        with open(args.f, 'r') as inFile:
            lines += map(lambda x: x.strip(), inFile.readlines())

    # 去重 / Remove duplicates
    lines = list(set(lines))
    for host in lines:
        if host:
            task_queue.put(host)

    return True


def consumer(bar):
    while True:
        try:
            target = task_queue.get(timeout=0.5)
        except:
            if task_queue.empty():
                break

        thread_worker(target)
        # 显示进度 / Show the progress
        lock.acquire()
        bar()
        lock.release()


def get_nodes(host):
    req_url = 'https://wepcc.com:443/'
    req_headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    param_body = {
        "host": host,
        "node": "1,2,3,4,5,6,7,8"
    }
    node_pattern = re.compile(r'data-id="(\w+?)"')
    try:
        req = requests.post(url=req_url, headers=req_headers, data=param_body)
        if req.status_code == 200:
            return node_pattern.findall(req.text)
        else:
            print(f"获取节点错误:{req.status_code}")  # Get nodes error
    except Exception as e:
        print(e)
    return []


def thread_worker(host):
    nodes = get_nodes(host)
    my_set = set()
    try:
        jobs = [gevent.spawn(gevent_worker, host, node, my_set)
                for node in nodes]
        gevent.joinall(jobs, timeout=20)
        # print([job.value for job in jobs])
        if my_set:
            isCdn = True if len(my_set) > 1 else False
        else:
            isCdn = '错误'  # Error
        result = {'host': host, 'isCdn': isCdn, 'ip': my_set}
        print(result)
        # 将结果放入结果队列 / Put the result into result_queue
        result_queue.put(result)

    except Exception as e:
        print('[线程工作错误]: {}'.format(e))


def gevent_worker(host, node, my_set):
    req_url = 'https://wepcc.com:443/check-ping.html'
    req_headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    param_body = 'node={n}&host={h}'.format(n=node, h=host)
    try:
        req = requests.post(url=req_url, data=param_body, headers=req_headers)
        if req.status_code == 200:
            try:
                json_data = json.loads(req.content)
                if json_data.get("code") == 0:
                    return False
                elif json_data.get("msg") == 'ok':
                    ip = json_data['data']['Ip']
                    my_set.add(ip)
                    return True
                else:
                    print(f"{host}:{json_data.get('msg')}")
                return False
            except Exception as e:
                print('[Gevent 工作线程解析 {host} Json 错误]: {error}'.format(
                    host=host, error=e))
        else:
            print(req.status_code)
    except Exception as e:
        print('[主程序 Gevent 工作线程错误]: {}'.format(e))
        time.sleep(0.5)

    return False


def parse_args():
    parser = ArgumentParser(
        prog='morePing',
        formatter_class=RawTextHelpFormatter,
        description='* 高速 CDN 检测工具 *\n',
        usage='morePing.py [选项]',
    )
    parser.add_argument(
        '--host',
        metavar='HOST',
        type=str,
        default='',
        help='从命令行扫描主机 / Scan host from command line',
    )
    parser.add_argument(
        '-f',
        metavar='TargetFile',
        type=str,
        default='',
        help='从目标文件加载新行分隔的目标 / Load new line delimited targets from TargetFile',
    )
    parser.add_argument(
        '-p',
        metavar='PROCESS',
        type=int,
        default=10,
        help='并发运行的进程数量，默认为 10 / Number of processes running concurrently, 10 by default',
    )
    parser.add_argument(
        '--force', action='store_true', help='强制从不规则文本中提取主机 / Force to extract host from irregular Text'
    )
    parser.add_argument('-v', action='version',
                        version='%(prog)s 1.1.0 By codervibe')

    if len(sys.argv) == 1:
        sys.argv.append('-h')
    args = parser.parse_args()
    check_args(args)
    return args


def check_args(args):
    if not args.host and not args.f:
        msg = '参数缺失！--host baidu.com 或 -f host.txt 未找到 / Args missing! --host baidu.com or -f host.txt not found'
        print(msg)
        exit(-1)

    if args.f and not os.path.isfile(args.f):
        print('目标文件未找到: {file}'.format(file=args.f))  # TargetFile not found


def main():
    args = parse_args()
    print('* MorePing v1.0  https://github.com/xq17/MorePing *')
    print('* 准备生成任务..... * / * preparing to generate task..... *')
    format_producer(args)
    target_count = task_queue.qsize()
    print('{} 个目标已进入队列. / {} targets entered Queue.'.format(target_count, target_count))
    thread_count = args.p
    print('创建 {} 个子进程... / Creating {} sub Processes...'.format(thread_count, thread_count))
    scan_process = []
    print('报告线程正在运行... / Report thread running...')
    global STOP_THIS
    STOP_THIS = False

    threading.Thread(target=report_result).start()
    try:
        with alive_bar(target_count) as bar:
            for _ in range(thread_count):
                t = threading.Thread(target=consumer, args=(bar,), daemon=True)
                t.start()
                scan_process.append(t)
            print('{} 个子进程成功启动. / {} sub processes started successfully.'.format(thread_count, thread_count))
            for t in scan_process:
                t.join()
    except KeyboardInterrupt as e:
        time.sleep(0.5)
        print('[+] 用户中断，子扫描进程退出.. / [+] User interrupted, child scan processes exit..')

    except Exception as e:
        print('[__main__.异常]: {type} {error}'.format(
            type=type(e), error=e))

    # 将结果输出到文件 / Output result to file
    STOP_THIS = True
    time.sleep(1)


if __name__ == "__main__":
    main()
