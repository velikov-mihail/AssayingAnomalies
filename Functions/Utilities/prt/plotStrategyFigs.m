function plotStrategyFigs(res)
% PURPOSE: Utility function to plot an optional figure in runUnivSort()
%------------------------------------------------------------------------------------------
% USAGE:   
% plotStrategyFigs(res)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -res - a structure output by runUnivSort()
%------------------------------------------------------------------------------------------
% Output:
%        -N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% plotStrategyFigs(res)
%------------------------------------------------------------------------------------------
% Dependencies:
%       Used by runUnivSort()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.


r = res.pret(:,end);
dates = res.dates;

ind=~isnan(r);
r=r(ind);
dates=dates(ind);
dt_dates=datetime(100*dates+1,'ConvertFrom','yyyyMMdd');
% str_dates = cellstr(dt_dates);

% Total log return
subplot(2,2,1); 
R = log(cumprod(r(~isnan(r))+1));
plot(dt_dates,R, '-r*')
title('Cumulative return (in logs)');
xlabel('date');
% res.ts = timeseries(R,str_dates,'name','total return (in logs)');

% 5 year rolling sharpe ratio
subplot(2,2,2);
sr = [];
if rows(r)>60
    for t = 61:rows(r)
        m = nanmean(r(t-60:t,:));
        st = nanstd(r(t-60:t,:));
        sr(t,1) = sqrt(12)*m/st ;
    end
end
sr(1:60,:) = nan ;
sr(isinf(sr)) = nan ;
res.srts = sr ;
plot(dt_dates,sr, '-r*')
xlabel('date');
title('5-year rolling Sharpe ratio');
% res.ts2 = timeseries(sr,str_dates,'name','5 year rolling Sharpe Ratio');


subplot(2,2,3)
nn = res.ptfNumStocks(ind,end);
plot(dt_dates,nn)
xlabel('date');
title('# of stocks');
% res.ts3 = timeseries(nn(nn>0),str_dates(nn>0),'name','# of stocks');



% Returns by year
subplot(2,2,4);
yrs=year(dt_dates);
f = min(yrs);
to = max(yrs);

M= []; 
for j = f:to  
    rr = r(yrs==j); 
    rr = cumprod(rr+1) - 1; 
    M = [M ; rr(end)]; 
end

y = (f:to)';
y = y(~isnan(M));
M = M(~isnan(M))*100;
bar(y,M); 
legend('annual %'); 
xlabel('year');
title('Returns by year');

