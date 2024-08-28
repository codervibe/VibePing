# VibePing
* 基于Python 多线程+多协程实现高并发查询API接口进行多地Ping Host来确认IP的真实归属。
~~~
git clone https://github.com/codervibe/VibePing.git
cd VibePing
pip install -r requirements.txt
python3 main.py
~~~
### Usage
~~~shell
python3 main.py 
usage: morePing.py [options]

* 一种高速CDN检测器 / A high-speed CDN detector *

options:
  -h, --help     show this help message and exit
  --host HOST    从命令行扫描主机/Scan host from command line
  -f TargetFile  从TargetFile加载新的行分隔的目标/Load newline-separated targets from TargetFile
  -p PROCESS     并发运行的进程数,默认为10/Number of concurrent processes, default is 10
  --force        强制从不规则文本中提取主机/Force extraction of hosts from irregular text
  -v             show program's version number and exit
~~~

#### Example

```
1.检查版本
	python3 main.py -v
2.检查单机
	python3 main.py --host baidu.com
3.从常规文件中检查更多主机
	python3 main.py -f hosts.txt -p 8
4. 检查主机是否有紊乱和混乱的文件 (定期自动匹配主机)
	python3 main.py -f other.txt --force -p 8
```
### update 
* 增强线程和协程的管理逻辑，确保在异常情况下能够安全退出。