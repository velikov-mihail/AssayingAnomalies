function gibbs=makeGibbs(fileName)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% This function reads in the Gibbs Effective Spread (!!!) measure from
% Hasbrouck (JF, 2009)

tic;
fprintf('Starting Gibbs construction at:\n');
disp(datetime('now'));

opts=detectImportOptions(fileName);
data=readtable(fileName,opts);
data=data(:,{'permno','year','c'});
data(isnan(data.c),:) = [];

load permno
load dates
load ret

gibbs = nan(size(ret));

for i = 1:size(data,1)
    rs = find(floor(dates/100) == data.year(i));
    c = find(permno == data.permno(i));
    gibbs(rs,c) = data.c(i);
end

gibbs=2*gibbs; % Multiply by 2 to be consistent with the other spread measures. We'll divide by two later.

fprintf('Done with Gibbs at:\n');
disp(datetime('now'));
toc



