function testCRSPData(Params)
% PURPOSE: This function runs and prints results in the command window from
% several tests which ensure that the MATLAB asset pricing package has run
% as it should have up to this point.
%------------------------------------------------------------------------------------------
% USAGE:   
% testCRSPData(Params)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -Params - a structure containing input parameter values
%             -Params.directory - directory where the setup_library.m was unzipped
%             -Params.username - WRDS username
%             -Params.pass - WRDS password 
%             -Params.domesticCommonEquityShareFlag - flag indicating whether to leave domestic common share equity (share code 10 or 11) only
%             -Params.SAMPLE_START - sample start date
%             -Params.SAMPLE_END - sample end dates
%             -Params.COMPUSTATVariablesFileName - Either name of file ('COMPUSTAT Variable Names.csv' included with library) or 'All' to download all ~1000 COMPUSTAT variables.
%             -Params.driverLocation - location of WRDS PostgreSQL JDBC Driver (included with library)
%             -Params.tcosts - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% testCRSPData(Params)             
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses makeBivSortInd(), runBivSort()
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.


% Test that your data matches up with some reference data 
load me
load ret
load ff
fprintf('\n\n\nRegress the Fama-French mkt on our mkt:\n');
lagMe = lag(me, 1, nan);
sumLagMe = sum(lagMe .* isfinite(ret), 2, 'omitnan');
MKT = sum(lagMe .* ret, 2, 'omitnan') ./ sumLagMe - rf;
prt(nanols(mkt,[.01*ones(size(mkt)) MKT]));

load ret_x_dl
fprintf('\n\n\nRegress the Fama-French mkt on our mkt, constructed using returns that are not adjusted for delisting:\n');
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
[res, ~] = runBivSort(ret, ind, 2, 3, dates, me); 

% Replicate UMD
umdrep = (res.pret(:,3) + res.pret(:,6) - ...
         (res.pret(:,1) + res.pret(:,4)) )/2;

fprintf('\n\nLook at the correlation between UMD from Ken French and replicated UMD:\n');
indFin = isfinite(sum([umdrep umd], 2));
corrcoef([umdrep(indFin) umd(indFin)]) % correlation shoud be > 99%

fprintf('\n\nCompare the average return UMD from Ken French and replicated UMD:\n');
prt(nanols(umd(indFin),[const(indFin)])) 
prt(nanols(umdrep(indFin),[const(indFin)]))

fprintf('\n\nRegress the two on each other:\n');
prt(nanols(umd,[const umdrep]))
prt(nanols(umdrep,[const umd]))

