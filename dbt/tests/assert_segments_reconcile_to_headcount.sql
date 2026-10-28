-- Every employee lands in exactly one segment: segment headcounts must sum to the staging row count.
select s.total_in_segments, e.total_employees
from (select sum(headcount) as total_in_segments from {{ ref('fct_attrition_segments') }}) s
cross join (select count(*) as total_employees from {{ ref('stg_hris__employees') }}) e
where s.total_in_segments <> e.total_employees
