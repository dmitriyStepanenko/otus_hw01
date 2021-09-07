import configparser
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from log_analyzer import parse_log_line
from log_analyzer import get_last_log_file_name
from log_analyzer import ParsedLine
from log_analyzer import FileNameWithDate
from log_analyzer import main
from log_analyzer import render_and_save_report
from log_analyzer import calc_stats
from log_analyzer import make_stats_table
from log_analyzer import update_configuration


class TestLogAnalyzer(unittest.TestCase):
    def test_log_analyzer(self):
        config = {
            "REPORT_SIZE": 1000,
            "REPORT_DIR": "./reports",
            "LOG_DIR": "./log",
            "PERCENT_PARSING_ERRORS": 5,
            'LOG_FILE_PATH': None
        }
        main(configuration=config)

    def test_update_configuration(self):
        new_config = configparser.ConfigParser()
        new_config.add_section('settings')
        new_config.set('settings', "REPORT_SIZE", "2")
        new_config.set('settings', "REPORT_SIZE", "5")
        new_config.set('settings', "REPORT_DIR", "./1_reports")
        new_config.set('settings', "LOG_DIR", "./1_log")
        new_config.set('settings', "PERCENT_PARSING_ERRORS", "3")
        new_config.set('settings', 'LOG_FILE_PATH', './own_log')

        path_to_config = Path(__file__).parent / 'config.txt'
        with open(path_to_config, 'w') as f:
            new_config.write(f)

        with patch.object(sys, 'argv', ['--config tests/config.txt']):
            configuration = update_configuration(configuration={
                "REPORT_DIR": "./_reports",
                "LOG_DIR": "./_log",
                "PERCENT_PARSING_ERRORS": 10,
                'LOG_FILE_PATH': None
            })
        self.assertEqual(
            {
                "REPORT_SIZE": 5,
                "REPORT_DIR": "./1_reports",
                "LOG_DIR": "./1_log",
                "PERCENT_PARSING_ERRORS": 3,
                'LOG_FILE_PATH': './own_log'
            },
            configuration
        )

    def test_get_last_log_file_name(self):
        self.assertEqual(None, get_last_log_file_name('./reports'))
        self.assertEqual(
            FileNameWithDate(
                name=(Path(__file__).parent.parent / 'log' / 'nginx-access-ui.log-20170630.gz').__str__(),
                date='20170630',
            ),
            get_last_log_file_name('./log')
        )

    def test_parse_log_line(self):
        self.assertEqual(None, parse_log_line(line=''))
        self.assertEqual(
            ParsedLine(url='some_url', request_time=0.1),
            parse_log_line(line='... ".. some_url ..." "..." 0.1'))

    def test_make_stats_table(self):
        table = [
            {'url': 'url1',
             'count': 2,
             'count_perc': round(2 / 3, 3),
             'time_sum': round(0.2, 3),
             'time_perc': round(0.2 / 0.5, 3),
             'time_avg': round(0.1, 3),
             'time_max': round(0.1, 3),
             'time_med': round(0.1, 3)
             },
            {'url': 'url2',
             'count': 1,
             'count_perc': round(1 / 3, 3),
             'time_sum': round(0.3, 3),
             'time_perc': round(0.3 / 0.5, 3),
             'time_avg': round(0.3, 3),
             'time_max': round(0.3, 3),
             'time_med': round(0.3, 3)
             }
        ]
        self.assertEqual(table, make_stats_table(log_data=[('url1', [0.1, 0.1]),
                                                           ('url2', [0.3])],
                                                 count_requests=3, sum_requests_time=0.5))

    def test_calc_stats(self):
        self.assertEqual(
            {'count': 2,
             'count_perc': round(0.5, 3),
             'time_sum': round(0.2, 3),
             'time_perc': round(0.2 / 0.5, 3),
             'time_avg': round(0.1, 3),
             'time_max': round(0.1, 3),
             'time_med': round(0.1, 3)
             },
            calc_stats([0.1, 0.1], 4, 0.5)
        )

    def test_render_reports(self):
        path_to_report = './reports/rendered_report.html'
        assert not Path(path_to_report).exists()
        render_and_save_report(table=[], path_to_report=path_to_report)
        assert Path(path_to_report).exists()
        Path(path_to_report).unlink(missing_ok=True)
