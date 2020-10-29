# -*- coding: utf-8 -*-

import datetime
import json
import logging
import requests
import sys
import time

# 停止条件
MAX_DIG_LAYER_NUM = 112300  # 最大目标层数
MIN_CHUTOU_NUM = 3000  # 最小锄头数
MIN_LINE_TNT_NUM = 2000  # 最小一字型炸药数
MIN_JGG_TNT_NUM = 1000  # 最小九宫格炸药数
DIG_TIME = 3000  # 脚本运行时间，单位是秒
MAX_STEP = 300  # 脚本最大循环执行步数

# 接口调用gap时间，减压防封，单位是秒
GAP_TIME = 1

# 棋盘长度
GAME_LENGTH = 7

# 工具使用
# 使用九宫格tnt的条件：
USE_JGG_TNT_LAND_LIMIT = 7  # 至少有7块包围土 or
USE_JGG_TNT_GIFT_LIMIT = 3  # 至少包含3个礼物
# 使用一字型tnt的条件：
USE_LINE_TNT_BESIDE_LAND_LIMIT = 11  # 所在层的上下两层的土块数多于此变量 and
USE_LINE_TNT_SELF_LAND_LIMIT = 4  # 自身所在行有效土块（不包括被岩石挡住的外边的土）多于此变量

ID = ""
G_TK = ""

# Cookies
COOKIES = {
    "pgv_pvi": "",
    "pgv_pvid": "",
    "pgv_info": "",
    "_qpsvr_localtk": "",
    "ptui_loginuin": ID,
    "uin": "o0" + ID,
    "skey": "",
    "RK": "",
    "ptcz": ""
}

# Other setting
OTHERS = {
    "content-type": "application/x-www-form-urlencoded",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36",
    "accept": "*/*",
    "origin": "http://appimg2.qq.com",
    "x-requested-with": "ShockwaveFlash/32.0.0.403",
    "sec-fetch-site": "cross-site",
    "sec-fetch-mode": "no-cors",
    "sec-fetch-dest": "empty",
    "referer": "http://appimg2.qq.com/card/swf/newLoader_v_133.swf",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-CN,zh;q=0.9"
}


# Game info
class GiftType(object):
    # To fill more
    gold_coin = 44  # 金币
    exp = 45  # 经验
    gold_powder = 47  # 金粉
    grade = 48  # 积分
    magic = 55  # 魔力值
    chutou = 65  # 锄头
    line_tnt = 66  # 一字型炸药
    super_tnt = 67  # 超级炸药
    jgg_tnt = 68  # 九宫格tnt
    gift = 70  # 占用背包的物品
    cash = 71  # 现金
    bottle = 75  # 漂流瓶

    @staticmethod
    def to_string(item):
        if item == GiftType.gold_coin:
            return "金币"
        elif item == GiftType.exp:
            return "经验"
        elif item == GiftType.gold_powder:
            return "金粉"
        elif item == GiftType.magic:
            return "魔力"
        elif item == GiftType.grade:
            return "积分"
        elif item == GiftType.chutou:
            return "锄头"
        elif item == GiftType.line_tnt:
            return "一字型炸药"
        elif item == GiftType.super_tnt:
            return "超级炸药"
        elif item == GiftType.jgg_tnt:
            return "九宫格炸药"
        elif item == GiftType.gift:
            return "占背包的礼物"
        elif item == GiftType.cash:
            return "现金"
        elif item == GiftType.bottle:
            return "漂流瓶"
        return "未知"


# 需要拾取的物品
NEED_GIFT = [GiftType.magic, GiftType.grade, GiftType.chutou, GiftType.line_tnt, GiftType.jgg_tnt, GiftType.super_tnt, GiftType.gift,
             GiftType.bottle]


class GiftId(object):
    # To fill more
    blue_stone = 3  # 蓝晶石
    green_stone = 4  # 绿晶石
    red_stone = 5  # 红晶石
    wood_block = 8  # 木板
    iron_block = 9  # 铁块


# 占用背包物品中需要过滤掉的
FILTER_GIFT = [GiftId.blue_stone, GiftId.green_stone, GiftId.red_stone]


class LandType(object):
    empty = 0  # 空
    soil = 2  # 土地，耗费1个锄头
    rock = 3  # 岩石，耗费2个锄头
    e_rock = 4  # 砸过一次的岩石，耗费1个锄头
    forbidden = 5  # 不可挖

    @staticmethod
    def to_string(item):
        if item == LandType.empty:
            return "空地"
        elif item == LandType.soil:
            return "土地"
        elif item == LandType.rock:
            return "岩石"
        elif item == LandType.e_rock:
            return "半岩石"
        elif item == LandType.forbidden:
            return "不可挖"
        return "未知"


class Act(object):
    meta = 1  # 获取信息
    dig = 2  # 挖地
    pick = 3  # 拾取


class DigType(object):
    chutou = 1  # 使用锄头
    line_tnt = 2  # 使用一字型炸药
    jgg_tnt = 3  # 使用九宫格炸药
    super_tnt = 4 # 使用超级炸药


class GameInfo(object):
    """游戏信息"""
    # 道具数量
    cash = 0  # 现金
    kuangshi_bi = 0  # 矿石币
    sui_jinshi = 0  # 碎晶石
    chutou = 0  # 锄头
    line_tnt = 0  # 一字型炸药
    jgg_tnt = 0  # 九宫格炸药
    # 地图信息
    page_index = 0  # 索引层数
    dig_index = 0  # 当前层数
    dig_info = {}  # 详细信息


class CardUtil(object):
    def __init__(self):
        self.init_http_session()
        self.init_game_info()

    @classmethod
    def init_http_session(cls):
        """
            初始化http session
        """
        requests.adapters.DEFAULT_RETRIES = 5  # 最大重连次数
        cls.session = requests.session()
        cls.session.keep_alive = False  # 关闭多余连接
        # 设置headers
        cls.headers = {"Connection": "close"}  # 调用结束即释放
        for header in OTHERS:
            cls.headers[header] = OTHERS[header]
        # 设置cookies
        for cookie in COOKIES:
            cls.session.cookies.set(cookie, COOKIES[cookie])

    @classmethod
    def init_game_info(cls):
        cls.game_info = GameInfo()
        cls.start_time = time.time()
        cls.cnt = 0

    @classmethod
    def set_game_info(cls, chutou, line_tnt, jgg_tnt, page_index, dig_index, dig_info):
        cls.game_info.chutou = chutou
        cls.game_info.line_tnt = line_tnt
        cls.game_info.jgg_tnt = jgg_tnt
        cls.game_info.page_index = page_index
        cls.game_info.dig_index = dig_index
        cls.game_info.dig_info = dig_info

    @classmethod
    def update_game_info(cls, line, col):
        line_str = str(line)
        if not cls.game_info.dig_info.get(line_str) or col >= len(cls.game_info.dig_info[line_str]):
            return
        if cls.game_info.dig_info[line_str][col].get("gift_id"):
            cls.game_info.dig_info[line_str][col]["gift_id"] = 0
        if cls.game_info.dig_info[line_str][col].get("gift_num"):
            cls.game_info.dig_info[line_str][col]["gift_num"] = 0
        if cls.game_info.dig_info[line_str][col].get("gift_type"):
            cls.game_info.dig_info[line_str][col]["gift_type"] = 0
        if cls.game_info.dig_info[line_str][col].get("type"):
            cls.game_info.dig_info[line_str][col]["type"] = 0

    @classmethod
    def get_meta_info(cls):
        time.sleep(GAP_TIME)
        url = "https://card.qzone.qq.com/cgi-bin/card_user_dig?g_tk=%s" % G_TK
        data = {"act": Act.meta}
        try:
            res = cls.session.post(url=url, data=data)
        except Exception:
            logging.error("请求异常，请求元信息失败")
            raise
        if res.status_code == 200:
            text = json.loads(res.text)
            if text["code"] == 0:
                cls.set_game_info(text["chutou"], text["line_tnt"], text["jgg_tnt"], text["page_index"],
                                  text["dig_index"], text["dig_info"])
                logging.info("获取元信息成功！当前层数%s" % text["dig_index"])
            else:
                logging.error("请求元信息失败")
                raise

    @classmethod
    def dig(cls, line, col, dig_type):
        time.sleep(GAP_TIME)
        url = "https://card.qzone.qq.com/cgi-bin/card_user_dig?g_tk=%s" % G_TK
        data = {"act": Act.dig, "line": line, "col": col, "dig_type": dig_type}
        try:
            res = cls.session.post(url=url, data=data)
        except Exception:
            logging.error("请求异常，挖地失败")
            raise
        if res.status_code == 200:
            text = json.loads(res.text)
            if text["code"] == 0:
                cls.set_game_info(text["chutou"], text["line_tnt"], text["jgg_tnt"], text["page_index"],
                                  text["dig_index"], text["dig_info"])
                logging.info("挖地成功！")
            else:
                logging.error("挖地失败")
                raise

    @classmethod
    def pick(cls, line, col):
        time.sleep(GAP_TIME)
        url = "https://card.qzone.qq.com/cgi-bin/card_user_dig?g_tk=%s" % G_TK
        data = {"act": Act.pick, "line": line, "col": col}
        try:
            res = cls.session.post(url=url, data=data)
        except Exception:
            logging.error("请求异常，拾取失败")
            raise
        if res.status_code == 200:
            text = json.loads(res.text)
            if text["code"] == 0:
                logging.info("拾取成功！")
                # 更新已经被拾取的位置
                cls.update_game_info(line, col)
            else:
                logging.error("拾取失败")
                raise

    @classmethod
    def is_stop(cls):
        """
            停止条件
        """
        if cls.cnt >= MAX_STEP:
            logging.info("已经达到运行步数！")
            return True
        if time.time() - cls.start_time > DIG_TIME:
            logging.info("已经达到运行时间！")
            return True
        if cls.game_info.dig_index >= MAX_DIG_LAYER_NUM:
            logging.info("已经挖到指定层数！")
            return True
        if cls.game_info.chutou <= MIN_CHUTOU_NUM:
            logging.info("已经达到最小剩余锄头数！")
            return True
        if cls.game_info.line_tnt <= MIN_LINE_TNT_NUM:
            logging.info("已经达到最小剩余一字型炸药数！")
            return True
        if cls.game_info.jgg_tnt <= MIN_JGG_TNT_NUM:
            logging.info("已经达到最小剩余九宫格型炸药数！")
            return True
        return False

    @classmethod
    def do_check_again(cls, line_index, col_index):
        # TODO
        """
            检查该块是否可以作为拾取对象，可拾取的条件为：
            1.该块是空地 or
            2.通过挖掘之后拾取，则可挖掘的条件为：
                1.该块是显示第一行，即 page_index + 1 or
                2.该块与第一行连通
        """
        return True

    @classmethod
    def is_pick(cls):
        """
            检查当前格子内是否有需要拾取的物品
        """
        dig_info = cls.game_info.dig_info
        for i in range(GAME_LENGTH):
            line = str(cls.game_info.page_index + 1 + i)
            # 遍历一行
            for col in dig_info[line]:
                if col.get("gift_type"):  # 该字段有值且不为0，说明有物品
                    # 如果是空地且有物品，直接拾取
                    if col["type"] == LandType.empty and col["gift_type"]:
                        return True, col["type"], int(line), int(col["j"]), int(col["gift_type"]), int(col["gift_id"]), int(col["gift_num"])
                    # 不是空地时，则判断物品是否需要，如果需要再拾取（拾取前需要挖掘）
                    if col["gift_type"] in NEED_GIFT and col["gift_id"] not in FILTER_GIFT:
                        # 如果就一个锄头，则不要
                        if col["gift_type"] == GiftType.chutou and col["gift_num"] == 1:
                            continue
                        # 检查这块是否可以作为拾取对象
                        if cls.do_check_again(int(line), int(col["j"])):
                            return True, col["type"], int(line), int(col["j"]), int(col["gift_type"]), int(col["gift_id"]), int(col["gift_num"])
        # 没有可以拾取的物品
        return False, 0, 0, 0, 0, 0, 0

    @classmethod
    def next_dig(cls, line, col):
        """
            向下挖时，扫描周围，决定使用何种工具进行挖掘
        """
        dig_info = cls.game_info.dig_info
        min_layer = cls.game_info.page_index + 1
        max_layer = cls.game_info.dig_index

        # 判断是否用九宫格炸药
        if min_layer + 1 < line < max_layer and 0 < col < GAME_LENGTH:
            check_list = [dig_info[str(line - 1)], dig_info[str(line)], dig_info[str(line + 1)]]
            check_col = [col - 1, col, col + 1]
            not_empty_land = 0
            has_gift = 0
            for line_item in check_list:
                for col_item in check_col:
                    if line_item[col_item].get("gift_type"):
                        has_gift += 1
                    if line_item[col_item]["type"] != LandType.empty and line_item[col_item]["type"] != LandType.forbidden:
                        not_empty_land += 1
            # 周围9块土的数量超过limit或者包含礼物超过limit，则使用九宫格炸药
            if not_empty_land >= USE_JGG_TNT_LAND_LIMIT or has_gift >= USE_JGG_TNT_GIFT_LIMIT:
                logging.info("【使用九宫格炸药】土块%s, 礼物%s, 行%s，列%s" %(str(not_empty_land), str(has_gift), str(line), str(col)))
                cls.dig(line, col, DigType.jgg_tnt)
                return

        # 判断是否使用一字型炸药，只在下挖时使用
        if dig_info[str(line + 1)][col]["type"] == LandType.forbidden:  # 如果下层不可挖，直接一字型tnt
            cls.dig(line, col, DigType.line_tnt)
            return
        check_list = [dig_info[str(line - 1)], dig_info[str(line + 1)]]
        not_empty_land = 0
        for line_item in check_list:
            for col_item in range(GAME_LENGTH):
                if line_item[col_item]["type"] != LandType.empty and line_item[col_item]["type"] != LandType.forbidden:
                    not_empty_land += 1

        self_land = 0
        line_item = dig_info[str(line)]
        i = col
        while 1:
            i -= 1
            if i < 0 or line_item[i]["type"] == LandType.forbidden or line_item[i]["type"] == LandType.rock:
                break
            if line_item[i]["type"] == LandType.soil or line_item[i]["type"] == LandType.e_rock:
                self_land += 1
        i = col
        while 1:
            i += 1
            if i >= GAME_LENGTH or line_item[i]["type"] == LandType.forbidden or line_item[i]["type"] == LandType.rock:
                break
            if line_item[i]["type"] == LandType.soil or line_item[i]["type"] == LandType.e_rock:
                self_land += 1
        # 上下两行土的数量之和超过limit并且自己所在行土的数量也超过limit，则使用一字型炸药
        if not_empty_land >= USE_LINE_TNT_BESIDE_LAND_LIMIT and self_land >= USE_LINE_TNT_SELF_LAND_LIMIT:
            logging.info("【使用一字型炸药】上下土块%s, 自身土块%s, 行%s，列%s" % (str(not_empty_land), str(self_land), str(line), str(col)))
            cls.dig(line, col, DigType.line_tnt)
            return

        # 使用锄头
        logging.info("【使用锄头】行%s，列%s" % (str(line), str(col)))
        cls.dig(line + 1, col, DigType.chutou)

    @classmethod
    def where_dig_next_layer(cls):
        """
            决定下一次下挖的列数
        """
        dig_info = cls.game_info.dig_info
        present_layer = dig_info[str(cls.game_info.dig_index)]
        # 对下一层的7个格子打分，取分数最高的作为接下来要挖掘的点，以挖最深和耗费资源最少为打分标准
        rank = [1, 2, 3, 4, 3, 2, 1]  # 基础分，当以下评判标准相同时尽量往中间挖
        for col in present_layer:
            if col["type"] == LandType.empty:
                next_layer = dig_info[str(cls.game_info.dig_index + 1)]
                next_next_layer = dig_info[str(cls.game_info.dig_index + 2)]
                if next_layer[col["j"]]["type"] == LandType.soil and next_next_layer[col["j"]]["type"] == LandType.empty:
                    rank[col["j"]] += 500
                elif next_layer[col["j"]]["type"] == LandType.e_rock and next_next_layer[col["j"]]["type"] == LandType.empty:
                    rank[col["j"]] += 400
                elif next_layer[col["j"]]["type"] == LandType.soil or next_layer[col["j"]]["type"] == LandType.e_rock:
                    rank[col["j"]] += 300
                elif next_layer[col["j"]]["type"] == LandType.rock and next_next_layer[col["j"]]["type"] == LandType.empty:
                    rank[col["j"]] += 200
                elif next_layer[col["j"]]["type"] == LandType.rock:
                    rank[col["j"]] += 100
            else:
                rank[col["j"]] = 0
        # 选得分最高者
        col_index = rank.index(max(rank))
        return col_index

    @classmethod
    def run_dig(cls):
        # 获取基础信息
        cls.get_meta_info()
        # print(cls.game_info.dig_info)
        while 1:
            # 检查停止条件
            if cls.is_stop():
                logging.info("停止条件满足，挖地停止！")
                break
            cls.cnt += 1
            logging.info("步数: %s" % str(cls.cnt))
            # 检查是否可以拾取
            is_pick, land_type, line, col, gift_type, gift_id, num = cls.is_pick()
            if is_pick:
                logging.info("行%s列%s有%s可拾取，数量为%s, 土地类型为%s" % (str(line), str(col), GiftType.to_string(gift_type), num, LandType.to_string(land_type)))
                # 空地则可直接拾取
                if land_type == LandType.empty:
                    # 如果是超级炸药，则调用挖地接口
                    if gift_type == GiftType.super_tnt:
                        cls.dig(line, col, DigType.super_tnt)
                    # 不是，则拾取
                    else:
                        logging.info("拾取中……")
                        cls.pick(line, col)
                # 非空地要先挖
                else:
                    logging.info("挖掘中……")
                    cls.dig(line, col, DigType.chutou)
            # 无可拾取物品，则选择下挖
            else:
                logging.info("选择下一层挖掘位置中……")
                col = cls.where_dig_next_layer()
                logging.info("下一层的挖掘起点为列%s" % str(col))
                logging.info("挖掘下一层中……")
                # 选择下挖时使用的工具
                cls.next_dig(cls.game_info.dig_index, col)


def log_init():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def main():
    logging.info("脚本执行 开始 %s" % (datetime.datetime.now()))
    try:
        card_util = CardUtil()
        card_util.run_dig()

    except Exception:
        logging.error("脚本执行失败")

    logging.info("脚本执行 结束 %s" % (datetime.datetime.now()))


if __name__ == '__main__':
    log_init()
    main()
