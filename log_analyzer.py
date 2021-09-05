#!/usr/bin/env python
# -*- coding: utf-8 -*-


# log_format ui_short '$remote_addr  $remote_user $http_x_real_ip [$time_local] "$request" '
#                     '$status $body_bytes_sent "$http_referer" '
#                     '"$http_user_agent" "$http_x_forwarded_for" "$http_X_REQUEST_ID" "$http_X_RB_USER" '
#                     '$request_time';
import gzip
import json
import sys
from configparser import ConfigParser
from string import Template
from collections import defaultdict, namedtuple
from typing import Dict, List, IO, Union
from pathlib import Path
from io import TextIOWrapper
import logging

config = {
    "REPORT_SIZE": 1000,
    "REPORT_DIR": "./reports",
    "LOG_DIR": "./log",
    "PERCENT_PARSING_ERRORS": 5,
    'LOG_FILE_PATH': None
}

DEFAULT_CONFIG_PATH = 'config.txt'
INT_SETTINGS = ['REPORT_SIZE', 'PERCENT_PARSING_ERRORS']
ParsedLog = namedtuple('ParsedLog', ['requests_times_by_url', 'sum_count_requests', 'sum_requests_time'])
FileNameWithDate = namedtuple('FileNameDate', ['name', 'date'])
IOWithDate = namedtuple('IOWithDate', ['io', 'date'])
ParsedLine = namedtuple('ParsedLine', ['url', 'request_time'])


def main(configuration: Dict):
    logging.basicConfig(
        format='[%(asctime)s] %(levelname).1s %(message)s',
        filename=configuration.get('LOG_FILE_PATH'),
        level='INFO'
    )
    try:
        configuration = update_configuration(configuration)

        log_file_io = get_log_file_io(log_dir=configuration['LOG_DIR'], report_dir=configuration['REPORT_DIR'])

        if log_file_io is not None:
            parsed_log = read_and_parse_log_file_io(
                log_file_io=log_file_io.io,
                report_size=configuration['REPORT_SIZE'],
                max_rel_parsing_errors=configuration['PERCENT_PARSING_ERRORS'])

            table = make_stats_table(log_data=parsed_log.requests_times_by_url,
                                     count_requests=parsed_log.sum_count_requests,
                                     sum_requests_time=parsed_log.sum_requests_time)
            report_name = f'report-{log_file_io.date[:4]}.{log_file_io.date[4:6]}.{log_file_io.date[6:]}.html'
            render_and_save_report(
                table=table,
                path_to_report=(Path(configuration['REPORT_DIR']) / report_name).__str__())

    except FileExistsError as e:
        logging.error(e)

    except Exception:
        logging.exception("Непредвиденная ошибка")


def update_configuration(configuration: Dict) -> Dict:
    if len(sys.argv) in [3, 4] and sys.argv[2] == '--config':
        config_from_file = ConfigParser()
        found_config = config_from_file.read(
            filenames=DEFAULT_CONFIG_PATH if len(sys.argv) == 3 else sys.argv[3],
            encoding='utf-8')
        if not found_config:
            raise FileExistsError(f'Не найден файл конфигурации "{DEFAULT_CONFIG_PATH}"')
        for key, val in config_from_file['settings'].items():
            configuration[key.upper()] = int(val) if key.upper() in INT_SETTINGS else val

    return configuration


def get_last_log_file_name(log_dir: str) -> Union[FileNameWithDate, None]:
    """
    Находит последний log файл
    """
    log_dir = Path(__file__).parent / log_dir

    if not log_dir.exists():
        return None

    prefix_file_name = 'nginx-access-ui.log-'
    date_format = 'yyyymmdd'
    slice_prefix = slice(len(prefix_file_name))
    slice_date = slice(len(prefix_file_name), len(prefix_file_name) + len(date_format))
    slice_format = slice(len(prefix_file_name) + len(date_format), 0)

    last_log_date = 0
    last_log_file = None
    for file_name in log_dir.iterdir():
        if not file_name.is_file():
            continue

        str_file_name = file_name.name

        if str_file_name[slice_prefix] != prefix_file_name or \
                str_file_name[slice_format] not in ['', '.gz'] or \
                not str_file_name[slice_date].isdigit():
            continue
        log_date = int(str_file_name[slice_date])
        if log_date > last_log_date:
            last_log_date = log_date
            last_log_file = file_name

    return FileNameWithDate(name=last_log_file.__str__(), date=str(last_log_date)) if last_log_file else None


def get_log_file_io(log_dir: str, report_dir: str) -> Union[IOWithDate, None]:
    """
    Готовит файл log-а для чтения
    """
    last_log_file = get_last_log_file_name(log_dir=log_dir)

    if last_log_file is None:
        logging.info('Не обнаружено ни одного файла log-а')
        return None

    if is_report_exist(log_date=last_log_file.date, report_dir=report_dir):
        logging.info(f'Для log-а с датой {last_log_file.date} найден ранее сформированный отчет')
        return None

    return IOWithDate(
        io=open(last_log_file.name) if last_log_file.name[-3:] == 'gz' else gzip.open(last_log_file.name),
        date=last_log_file.date,
    )


def read_and_parse_log_file_io(
        log_file_io: IO,
        report_size: int,
        max_rel_parsing_errors: float
) -> Union[ParsedLog, None]:
    """
    Читает данные из файла log-а и парсит их
    """
    requests_time_by_url: Dict[str, List[float]] = defaultdict(list)
    count_requests = 0
    sum_time = 0
    count_lines = 0
    count_parsing_error = 0

    with TextIOWrapper(log_file_io) as f:
        while len(requests_time_by_url) < report_size:
            line = f.readline()
            if not line:
                logging.info(f'В log файле url-ов меньше {report_size}')
                break
            count_lines += 1
            parsed_line = parse_log_line(line)
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
        logging.error(f'Процент ошибок парсинга log-а превышает допустимый '
                      f'установленный уровень в {max_rel_parsing_errors}%')
        return None

    logging.info(f'Парсинг успешно завершен, ошибок парсинга: {count_parsing_error}')
    return ParsedLog(requests_times_by_url=requests_time_by_url,
                     sum_count_requests=count_requests,
                     sum_requests_time=sum_time)


def is_report_exist(log_date, report_dir: str) -> bool:
    """
    Проверяет существует ли уже отчет для log-а с самой последней датой
    """
    report_dir = Path(__file__).parent / report_dir

    if not report_dir.exists():
        return False

    # sample report_name: "report-2017.06.30.html"
    report_name = f"report-{log_date[:4]}.{log_date[4:6]}.{log_date[6:]}.html"

    for file_name in report_dir.iterdir():
        if not file_name.is_file():
            continue
        if file_name.name == report_name:
            return True

    return False


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
        log_data: Dict[str, List[float]],
        count_requests: int,
        sum_requests_time: float
) -> List[Dict[str, str]]:
    """
    Формирует таблицу статистики по запросам
    """
    stats_table = []
    for url, times in log_data.items():
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
    main(config)
