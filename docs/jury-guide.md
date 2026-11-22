# Проверка решения

## Что показывают два сеанса

| Шаг | Что открыть | Что подтверждено |
| --- | --- | --- |
| Постановка задачи | [Бриф](../demo/megafon/brief.md) · [запрос первого сеанса](../evidence/megafon/v1-prompt.txt) | Руководителю нужен выбор пилота и план по пяти показателям. В историческом сеансе запрос уже структурирован. |
| Расчёт и решение v1 | [Запись вызова](../evidence/megafon/v1-calculator-trace-excerpt.json) · [расчёт](../continuation/case/baseline/model-result.json) · [ответ](../continuation/case/baseline/decision.md) | Агент вызвал локальный калькулятор и использовал результат, сравнил варианты и сохранил условную рекомендацию. |
| Продолжение | [Состояние](../continuation/case/baseline/state.json) · [новые данные](../continuation/case/update/recruitment.json) · [запрос второго сеанса](../continuation/prompt.txt) | Новый сеанс получает сохранённый результат и учебное ограничение: 150 семей в неделю. |
| Пересмотр | [Ответ v2](../continuation/case/results/decision-v2.md) · [запись изменений](../continuation/case/results/revision.json) · [сводка запуска](../continuation/case/results/summary.json) | Агент пересчитал срок и разделил проверку процесса и проверку эффекта. Срок, бюджет и запуск оставлены на решение руководителя. |
| Редакция команды | [Итоговая стратегия](megafon-submission-strategy.md) · [внешняя сверка](megafon-market-check.md) | После прогонов команда уточнила уведомление, условия паузы и остановки, когортную экономику и влияние сдвига срока. |

Скриншоты терминала: [первый запуск](../evidence/megafon/v1-windows.png) и [второй запуск](../evidence/megafon/v2-windows.png). В финальном ролике показаны сохранённые сеансы; фрагмент второго сеанса начинается примерно на 3:17. Описание работы: [PDF](MGIMO_MegaFon_Project_Description.pdf) или [DOCX](MGIMO_MegaFon_Project_Description.docx).

## Локальные проверки

Из корня репозитория, Python 3.10 или новее:

```sh
python -m unittest discover -s tests -v
python tools/operator_model.py demo/megafon/assumptions.json
python continuation/start.py --check
python tools/demo_megafon_review.py --choice observe
python tools/megafon_cohorts.py demo/megafon/cohorts-example.csv demo/megafon/costs-example.csv
python tools/megafon_delay.py demo/megafon/assumptions.json
```

В сухой проверке второго сеанса должно получиться **900 семей за 6 недель**, недобор **2 376**, **22 недели набора** и **7 дней наблюдения**. Когортная модель и сдвиг срока показывают чувствительность на синтетических входах.

Для отдельной проверки разрешённого публичного PDF:

```sh
python tools/check_megafon_source.py
```

Требуется доступ к `ceph.megafon.ru` и `pypdf` или `pdftotext`. Сохранённый [протокол](../evidence/megafon/public-web-receipt.json) подтверждает отдельный вызов скрипта. Он не подтверждает вызов сайта агентом во время исторических сеансов.

## Дополнительные сценарии и ограничения

- [Парные прогоны](paired-run-results.md) и [сравнение по трафику](traffic-comparison.md) относятся к вспомогательным учебным задачам.
- [Контрольный сценарий с QA](megafon-qa-rechallenge.md) подготовлен для нового сеанса; сохранённого модельного результата по нему нет.
- Исторические прогоны подтверждают логику работы агента на учебных данных. Идентификатор модели в журналах не зафиксирован; стоимость не измерена; эффект уведомления и окупаемость не доказаны. Ключи и персональные документы не требуются.
