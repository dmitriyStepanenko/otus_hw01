#!/usr/bin/env python
# -*- coding: utf-8 -*-


# log_format ui_short '$remote_addr  $remote_user $http_x_real_ip [$time_local] "$request" '
#                     '$status $body_bytes_sent "$http_referer" '
#                     '"$http_user_agent" "$http_x_forwarded_for" "$http_X_REQUEST_ID" "$http_X_RB_USER" '
#                     '$request_time';
import datetime
import gzip
import json
import argparse
import re
from configparser import ConfigParser
from string import Template
from collections import defaultdict, namedtuple
from typing import Dict, List, Union, Tuple, Callable
from pathlib import Path
from io import TextIOWrapper
from datetime import datetime
import logging

config = {
    "REPORT_SIZE": 1000,
    "REPORT_DIR": "./log",
    "LOG_DIR": "./log",
    "PERCENT_PARSING_ERRORS": 5,
    'LOG_FILE_PATH': None
}

DEFAULT_CONFIG_PATH = 'config.txt'
INT_SETTINGS = ['REPORT_SIZE', 'PERCENT_PARSING_ERRORS']
ParsedLog = namedtuple('ParsedLog', ['requests_times_by_url', 'sum_count_requests', 'sum_requests_time'])
FileNameWithDate = namedtuple('FileNameDate', ['name', 'date'])
ParsedLine = namedtuple('ParsedLine', ['url', 'request_time'])


def main(configuration: Dict):
    try:
        args = parse_sys_args()
        configuration = update_configuration(configuration, args.config)
        logging.basicConfig(
            format='[%(asctime)s] %(levelname).1s %(message)s',
            filename=configuration.get('LOG_FILE_PATH'),
            level='INFO'
        )

        last_log_file = get_last_log_file_name(log_dir=configuration['LOG_DIR'])

        if last_log_file is None:
            logging.info('Не обнаружено ни одного файла log-а')

        else:
            last_date: datetime = last_log_file.date
            report_name = f"report-{last_date.strftime('%Y.%m.%d')}.html"
            if (Path(__file__).parent / configuration['REPORT_DIR'] / report_name).exists():
                logging.info(f'Для log-а с датой {last_date} найден ранее сформированный отчет')

            else:
                parsed_log = read_and_parse_log_file(
                    log_file_name=last_log_file.name,
                    report_size=configuration['REPORT_SIZE'],
                    max_rel_parsing_errors=configuration['PERCENT_PARSING_ERRORS'],
                    line_parser=parse_log_line
                )

                table = make_stats_table(log_data=parsed_log.requests_times_by_url,
                                         count_requests=parsed_log.sum_count_requests,
                                         sum_requests_time=parsed_log.sum_requests_time)
                render_and_save_report(
                    table=table,
                    path_to_report=(Path(configuration['REPORT_DIR']) / report_name).__str__())

    except Exception as e:
        logging.exception(e if e.args else "Непредвиденная ошибка")
        raise


def parse_sys_args():
    argparser = argparse.ArgumentParser()
    argparser.add_argument('--config', type=str, default=DEFAULT_CONFIG_PATH)
    return argparser.parse_args()


def update_configuration(default_configuration: Dict, path_to_config: str) -> Dict:
    config_from_file = ConfigParser()
    found_config = config_from_file.read(
        filenames=DEFAULT_CONFIG_PATH if path_to_config is not None else path_to_config,
        encoding='utf-8')
    if not found_config:
        raise FileExistsError(f'Не найден файл конфигурации "{DEFAULT_CONFIG_PATH}"')
    for key, val in config_from_file['settings'].items():
        default_configuration[key.upper()] = int(val) if key.upper() in INT_SETTINGS else val

    return default_configuration


def get_last_log_file_name(log_dir: str) -> Union[FileNameWithDate, None]:
    """
    Находит последний log файл
    """
    log_dir = Path(__file__).parent / log_dir

    if not log_dir.exists():
        return None

    last_log_date = datetime.min
    last_log_file = None
    for file_name in log_dir.iterdir():
        if not file_name.is_file():
            continue

        log_file_re = re.match(r'^nginx-access-ui\.log-(?P<date>\d{8})(\.gz)?$', file_name.name)
        if log_file_re is None:
            continue

        log_date = datetime.strptime(log_file_re.group('date'), '%Y%m%d')
        if log_date > last_log_date:
            last_log_date = log_date
            last_log_file = file_name

    return FileNameWithDate(name=last_log_file.__str__(), date=last_log_date) if last_log_file else None


def read_and_parse_log_file(
        log_file_name: str,
        report_size: int,
        max_rel_parsing_errors: float,
        line_parser: Callable
) -> Union[ParsedLog, None]:
    """
    Читает данные из файла log-а и парсит их
    """
    requests_time_by_url: Dict[str, List[float]] = defaultdict(list)
    count_requests = 0
    sum_time = 0
    count_lines = 0
    count_parsing_error = 0

    with open(log_file_name) if log_file_name[-3:] == 'gz' else gzip.open(log_file_name) as log_file_io:
        with TextIOWrapper(log_file_io) as f:
            for _ in range(100000): #while True:
                line = f.readline()
                if not line:
                    break
                count_lines += 1
                parsed_line = line_parser(line)
                if parsed_line is None:
                    count_parsing_error += 1
                    continue
                url, request_time = parsed_line
                count_requests += 1
                sum_time += request_time
                requests_time_by_url[url].append(request_time)

    if count_lines == 0:
        logging.info('Файл log-а пуст')
        return None

    if count_parsing_error / count_lines > max_rel_parsing_errors:
        raise ValueError(f'Процент ошибок парсинга log-а превышает допустимый '
                         f'установленный уровень в {max_rel_parsing_errors}%')

    logging.info(f'Парсинг успешно завершен, ошибок парсинга: {count_parsing_error}')
    return ParsedLog(
        requests_times_by_url=sorted(requests_time_by_url.items(),
                                     key=lambda item: sum(item[1]),
                                     reverse=True)[:report_size],
        sum_count_requests=count_requests,
        sum_requests_time=sum_time)


def parse_log_line(line: str) -> Union[ParsedLine, None]:
    """
    Парсит одну строку из log-а.

    Все ошибки парсинга неважны, потом просто посчитаем количество ошибок.
    """
    try:
        line_parts = line.split('"')
        url = line_parts[1].split(' ')[1]
        request_time = float(line_parts[-1])
        return ParsedLine(url=url, request_time=request_time)
    except Exception:
        return None


def make_stats_table(
        log_data: List[Tuple[str, List[float]]],
        count_requests: int,
        sum_requests_time: float
) -> List[Dict[str, str]]:
    """
    Формирует таблицу статистики по запросам
    """
    stats_table = []
    for url, times in log_data:
        stats_table.append(
            {'url': url,
             **calc_stats(times=times,
                          count_requests=count_requests,
                          sum_time=sum_requests_time)
             }
        )

    return stats_table


def calc_stats(
        times: List[float],
        count_requests: int,
        sum_time: float
) -> Dict:
    """
    Вычисляет статистику для каждого запроса
    """
    current_sum_time = sum(times)
    return {
        'count': len(times),
        'count_perc': round(len(times) / count_requests, 3),
        'time_sum': round(current_sum_time, 3),
        'time_perc': round(current_sum_time / sum_time, 3),
        'time_avg': round(current_sum_time / len(times), 3),
        'time_max': round(max(times), 3),
        'time_med': round(sorted(times)[len(times) // 2], 3)
    }


def render_and_save_report(table: List[Dict], path_to_report: str):
    """
    Подставляет в шаблон отчета таблицу и сохраняет в папку для отчетов
    """
    file_report_template = Path(__file__).parent / 'report_template.html'

    with open(file_report_template, 'r', encoding='utf-8') as f:
        report = f.read()

    table_json = json.dumps(table)

    report_template = Template(report).safe_substitute(dict(table_json=table_json))

    Path(path_to_report).parent.mkdir(exist_ok=True)

    with open(Path(path_to_report), 'w', encoding='utf-8') as f:
        f.write(report_template)

    logging.info('Отчет успешно сформирован и сохранен')


if __name__ == "__main__":
    main(config.copy())
