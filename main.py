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
STOP_THIS = False


def report_result():
    dirPath = './report'
    if not os.path.exists(dirPath):
        os.mkdir(dirPath)

    cdnHost = os.path.join(dirPath, f'cdnHost_{time.strftime("%Y%m%d", time.localtime())}.txt')
    realHost = os.path.join(dirPath, f'realHost_{time.strftime("%Y%m%d", time.localtime())}.txt')
    errorHost = os.path.join(dirPath, f'errorHost_{time.strftime("%Y%m%d", time.localtime())}.txt')
    all_result = []

    global STOP_THIS

    try:
        while not STOP_THIS:
            if result_queue.empty():
                time.sleep(0.1)
                continue

            while not result_queue.empty():
                all_result.append(result_queue.get())

            cdn_text, real_text, error_text = '', '', ''
            for item in all_result:
                if item['isCdn'] is True:
                    cdn_text += f"{item['host']}\nip: {', '.join(item['ip'])}\n"
                elif item['isCdn'] is False:
                    real_text += f"{item['host']}\nip: {', '.join(item['ip'])}\n"
                else:
                    error_text += f"{item['host']}\n"

            try:
                with open(cdnHost, 'w') as f1, open(realHost, 'w') as f2, open(errorHost, 'w') as f3:
                    f1.write(cdn_text)
                    f2.write(real_text)
                    f3.write(error_text)
            except Exception as e:
                print(f"[保存结果时出错/Save result error]: {e}")

            # 清空已处理的结果 / Clear processed results
            all_result.clear()

        if all_result:
            print(f"[扫描报告保存到/Scan report saved to]: {cdnHost} {realHost} {errorHost}")
        else:
            print("[错误，结果为空/Error, results are empty]")
    except Exception as e:
        print(f"[保存结果线程错误/Error in result saving thread]: {e}")
        sys.exit(-1)


def format_producer(args):
    lines = []
    if args.host:
        lines.append(args.host.strip())

    if args.force and args.f:
        try:
            with open(args.f, 'r') as inFile:
                content = inFile.read()
            pattern = re.compile(
                r'([a-zA-Z0-9][-a-zA-Z0-9]{0,62}(\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+\.[a-z]+?)\s'
            )
            resList = pattern.findall(content)
            for h in resList:
                lines.append(h[0])
        except Exception as e:
            print(f'[错误强制模式/Error in force mode]: {e}')

    elif args.f:
        try:
            with open(args.f, 'r') as inFile:
                lines += [line.strip() for line in inFile.readlines()]
        except Exception as e:
            print(f'[文件读取错误/File reading error]: {e}')

    # 去重 / Remove duplicates
    lines = list(set(lines))
    for host in lines:
        if host:
            task_queue.put(host)

    return True


def consumer(bar):
    global target
    while True:
        try:
            target = task_queue.get(timeout=0.5)
        except queue.Empty:
            break

        thread_worker(target)

        # 进度条更新 / Update progress bar
        with lock:
            bar()


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
            print(f"获取节点错误: {req.status_code}/get_nodes Error: {req.status_code}")
    except Exception as e:
        print(f"[获取节点错误/Error getting nodes]: {e}")
    return []


def thread_worker(host):
    nodes = get_nodes(host)
    my_set = set()
    try:
        jobs = [gevent.spawn(gevent_worker, host, node, my_set) for node in nodes]
        gevent.joinall(jobs, timeout=20)

        isCdn = True if len(my_set) > 1 else (False if my_set else 'Error')
        result = {'host': host, 'isCdn': isCdn, 'ip': my_set}
        print(result)

        # 结果加入队列 / Add results to the queue
        result_queue.put(result)

    except Exception as e:
        print(f'[错误线程工作/Error in thread worker]: {e}')


def gevent_worker(host, node, my_set):
    req_url = 'https://wepcc.com:443/check-ping.html'
    req_headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    param_body = f'node={node}&host={host}'
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
                    print(f"{host}: {json_data.get('msg')}")
                return False
            except Exception as e:
                print(f'[错误解析 JSON {host}]: {e}/Error parsing JSON {host}: {e}')
        else:
            print(f"请求错误状态码: {req.status_code}/Request error status code: {req.status_code}")
    except Exception as e:
        print(f'[Gevent Worker 错误/Error in Gevent Worker]: {e}')
        time.sleep(0.5)
    return False


def parse_args():
    parser = ArgumentParser(
        prog='morePing',
        formatter_class=RawTextHelpFormatter,
        description='* 一种高速CDN检测器 / A high-speed CDN detector *\n',
        usage='morePing.py [options]',
    )
    parser.add_argument(
        '--host',
        metavar='HOST',
        type=str,
        default='',
        help='从命令行扫描主机/Scan host from command line',
    )
    parser.add_argument(
        '-f',
        metavar='TargetFile',
        type=str,
        default='',
        help='从TargetFile加载新的行分隔的目标/Load newline-separated targets from TargetFile',
    )
    parser.add_argument(
        '-p',
        metavar='PROCESS',
        type=int,
        default=10,
        help='并发运行的进程数，默认为10/Number of concurrent processes, default is 10',
    )
    parser.add_argument(
        '--force', action='store_true', help='强制从不规则文本中提取主机/Force extraction of hosts from irregular text'
    )
    parser.add_argument('-v', action='version', version='%(prog)s 1.0    By xq17')

    if len(sys.argv) == 1:
        sys.argv.append('-h')
    args = parser.parse_args()
    check_args(args)
    return args


def check_args(args):
    if not args.host and not args.f:
        print('Args失踪!——请使用 --host baidu.com 或 -f host.txt 指定目标/Args missing! Use --host baidu.com or -f host.txt to specify targets')
        exit(-1)

    if args.f and not os.path.isfile(args.f):
        print(f'目标文件未找到: {args.f}/Target file not found: {args.f}')


def main():
    args = parse_args()
    print('* MorePing v1.0  https://github.com/xq17/MorePing *')
    print('* 正在准备生成任务... / Preparing to generate tasks... *')
    format_producer(args)
    target_count = task_queue.qsize()
    print(f'{target_count} 个目标已加入队列./{target_count} targets entered the queue.')
    thread_count = args.p
    print(f'创建 {thread_count} 个子进程.../Creating {thread_count} subprocesses...')
    scan_process = []
    print('报告线程正在运行.../Report thread is running...')
    global STOP_THIS
    STOP_THIS = False

    threading.Thread(target=report_result).start()
    try:
        with alive_bar(target_count) as bar:
            for _ in range(thread_count):
                t = threading.Thread(target=consumer, args=(bar,), daemon=True)
                t.start()
                scan_process.append(t)
            print(f'{thread_count} 个子进程正在运行./{thread_count} subprocesses are running.')
            for t in scan_process:
                t.join()
    except KeyboardInterrupt:
        print('[+] 用户中止，子扫描进程已退出.../User interrupted, subprocesses exited...')
    except Exception as e:
        print(f'[主进程错误/Error in main process]: {type(e)} {e}')

    STOP_THIS = True
    time.sleep(1)


if __name__ == '__main__':
    main()
