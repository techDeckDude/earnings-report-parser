-- this query shows the number of metrics in an earnings report
-- grouped by company. Useful for understanding how many rows
-- are needed to store a single earnings report for a company
select c.name as company_id,
    er.period as earnings_report_id,
    count(distinct fm.metric_name)
from companies as c
    join earnings_reports as er on c.id = er.company_id
    join financial_metrics as fm on er.id = fm.report_id
group by er.id;

SELECT c.ticker, c.name, COUNT(er.id) AS filings, MIN(er.period) AS earliest, MAX(er.period) AS latest
   FROM companies c
   LEFT JOIN earnings_reports er ON c.id = er.company_id
   GROUP BY c.id
   ORDER BY c.ticker;