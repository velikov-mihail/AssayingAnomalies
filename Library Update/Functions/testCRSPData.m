function testCRSPData()
% PURPOSE: This function runs and prints results in the command window from
% several tests which ensure that the MATLAB asset pricing package has run
% as it should have up to this point.
%------------------------------------------------------------------------------------------
% USAGE:   
% testCRSPData()
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -None
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% testCRSPData()             
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses makeBivSortInd(), runBivSort()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on testing the CRSP data at %s.\n', char(datetime('now')));

% Test that your data matches up with some reference data 
load me
load ret
load ff
fprintf('\nRegress the Fama-French MKT on our MKT:\n');
lagMe = lag(me, 1, nan);
sumLagMe = sum(lagMe .* isfinite(ret), 2, 'omitnan');
MKT = sum(lagMe .* ret, 2, 'omitnan') ./ sumLagMe - rf;
prt(nanols(mkt,[.01*ones(size(mkt)) MKT]));

load ret_x_dl
fprintf('Regress the Fama-French MKT on our MKT, constructed using returns that are not adjusted for delisting:\n');
lagMe = lag(me, 1, nan);
sumLagMe = sum(lagMe .* isfinite(ret_x_dl), 2, 'omitnan');
MKT = sum(lagMe .* ret_x_dl, 2, 'omitnan') ./ sumLagMe - rf;
prt(nanols(mkt,[.01*ones(size(mkt)) MKT]));

% Replicate umd factor
load R
load dates
load NYSE
load ret
ind = makeBivSortInd(me, 2, R, [30 70], 'sortType', 'unconditional', ...
                                        'breaksFilter', NYSE);      
[res, ~] = runBivSort(ret, ind, 2, 3, dates, me, 'printResults', 0, ...
                                                 'plotFigure', 0); 

% Replicate UMD
umdrep = (res.pret(:,3) + res.pret(:,6) - ...
         (res.pret(:,1) + res.pret(:,4)) )/2;

% Look at correlation between UMD and replication
indFin = isfinite(sum([umdrep umd], 2));
temp = corrcoef([umdrep(indFin) umd(indFin)]); % correlation shoud be > 99%
fprintf('The correlation between UMD from Ken French and replicated UMD is %.2f%%.\n', 100*temp(1,2));

fprintf('\nCompare the average return UMD from Ken French and replicated UMD:\n');
prt(nanols(umd(indFin),[const(indFin)])) 
prt(nanols(umdrep(indFin),[const(indFin)]))

fprintf('Regress the two on each other:\n');
prt(nanols(umd,[const umdrep]))
prt(nanols(umdrep,[const umd]))

