function hf_spreads=makeHighFreqEffSpreads()
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% This functions create the high-frequency (TAQ + ISSM) Effective Spreads (!!!) 

tic;
fprintf('Starting TAQ+ISSM spread construction at:\n');
disp(datetime('now'));


load permno
load dates
load ret

if exist('hf_monthly.csv')
    opts=detectImportOptions('hf_monthly.csv');
    data=readtable('hf_monthly.csv',opts);
else
    error(['File hf_monthly.csv does not exists. High-frequency trading cost estimate cannot be constructed']);
end

data=data(:,{'permno','yearm','espread_pct_mean','espread_pct_month_end','espread_n'});
data.Properties.VariableNames={'permno','date','ave','monthend','n'};

hf_spreads=struct;
hf_spreads.ave=nan(size(ret));
hf_spreads.monthend=nan(size(ret));
hf_spreads.n=nan(size(ret));

for i=1:height(data)  
    r=find(dates==data.date(i));
    c=find(permno==data.permno(i));
    if isfinite(r+c)
        hf_spreads.ave(r,c)=data.ave(i)/100;
        hf_spreads.monthend(r,c)=data.monthend(i);
        hf_spreads.n(r,c)=data.n(i);
    end
end

fprintf('Done with high-frequency spreads at:\n');
disp(datetime('now'));
toc

