# Анализатор лога

Скрипт подготавливает данные для анализа url-ов на "подозрительность" из последнего log-а.

Для каждого url-а собирается статистика:
* count - сколько раз встречается URL, абсолютное значение
* count_perc - сколько раз встречается URL, в процентнах относительно общего числа запросов
* time_sum - суммарный $request_time для данного URL'а, абсолютное значение
* time_perc - суммарный $request_time для данного URL'а, в процентах относительно общего $request_time всех запросов
* time_avg - средний $request_time для данного URL'а
* time_max - максимальный $request_time для данного URL'а
* time_med - медиана $request_time для данного URL'а

Результатом работы является отчет в формате html.

## Запуск
```
python log_analyzer.py
```
Все логи должны лежать в папке ./log
Отчет можно будет найти в папке ./reports
Скрипт пишет собственные логи в консоль

Для изменения параметров конфигурации скрипта можно использовать --config
```
python log_analyzer.py --config
# или так если хочется указать путь
python log_analyzer.py --config path_to_config/config.txt
```
Настраиваемые параметры конфигурации:
- "REPORT_SIZE" - количество url-ов в отчете
- "REPORT_DIR" - путь до папки с отчетом
- "LOG_DIR" - путь до папки с логами
- "PERCENT_PARSING_ERRORS" - процент ошибок парсинга log-а 
- 'LOG_FILE_PATH' - путь до файла собственного log-а

Пример config.txt
```
[settings]
REPORT_SIZE=1100
```

## Запуск тестов
```
python -m unittest tests/test.py
```