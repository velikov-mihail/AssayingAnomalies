function makeFFTcosts()
% PURPOSE: This function creates the trading costs for the FF factors
% following Detzel, Novy-Marx, and Velikov (2022)
%------------------------------------------------------------------------------------------
% USAGE:   
% makeTCosts(Params)              % Creates the trading costs measures
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -None
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% makeFFTcosts()              
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses makeBivSortInd(), makeFactorTcosts(), runUnivSort()
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Detzel, A., Novy-Marx, R., and M. Velikov, 2022, Model Comparison 
%  with Trading Costs, Working paper.
%  2. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.


% Load the variables necessary for replication
load ret
load me
load BE
load R
load NYSE
load dates
load tcosts
load ff
load AT
load revt
load cogs
load xint
load xsga
load be
load FinFirms

% Book-to-market
btm = BE./lag(me, 6, nan);

% Operating Profitability = (REVT - COGS - XSGA - XINT)\/BE
OP = REVT + nanmatsum(-COGS, -nanmatsum(XSGA, XINT));
OpProf = OP./BE;

% Negative of asset growth (AT/AT_{-12})
inv = -AT./lag(AT, 12, nan);

% Get the indices & weight matrices for the makeFactorTcosts function
% SMB & HML
indFF93 = makeBivSortInd(me, 2, ...
                         btm, [30 70], ...
                         'sortType', 'unconditional', ...
                         'breaksFilterInd', NYSE);

% Carry over the portflio indices from June to the other months
tempInd = indFF93;
indNoReb = sum(tempInd,2) == 0;
tempInd(indNoReb, :) = nan;
tempInd = FillMonths(tempInd);

% Inialize the weights matrix & store a couple of constants
wFF93 = nan(size(ret));
nPtf = max(max(indFF93));
nStocks = size(ret, 2);

% Loop over the portfolios
for i = 1:nPtf
    % Calculate the weights based on the market cap for this portfolio
    tempMe = me;
    tempMe(tempInd ~= i) = nan;
    sumTempMe = sum(tempMe, 2, 'omitnan');
    rptdTempMe = repmat(sumTempMe, 1, nStocks);
    tempW = tempMe ./ rptdTempMe;
    wFF93(tempInd==i) = tempW(tempInd==i);
end

% RMW
indMEOpProf = makeBivSortInd(me, 2, ...
                             OpProf, [30 70], ...
                             'sortType', 'unconditional', ...
                             'breaksFilterInd', NYSE);

% Carry over the portflio indices from June to the other months
tempInd = indMEOpProf;
indNoReb = sum(tempInd,2) == 0;
tempInd(indNoReb, :) = nan;
tempInd = FillMonths(tempInd);

% Inialize the weights matrix & store a couple of constants
wMeOpProf = nan(size(ret));
                   
% Loop over the portfolios
for i = 1:nPtf
    % Calculate the weights based on the market cap for this portfolio
    tempMe = me;
    tempMe(tempInd ~= i) = nan;
    sumTempMe = sum(tempMe, 2, 'omitnan');
    rptdTempMe = repmat(sumTempMe, 1, nStocks);
    tempW = tempMe ./ rptdTempMe;
    wMeOpProf(tempInd==i) = tempW(tempInd==i);
end

% CMA
indMeInv = makeBivSortInd(me, 2, ...
                          inv, [30 70], ...
                          'sortType', 'unconditional', ...
                          'breaksFilterInd', NYSE);

% Carry over the portflio indices from June to the other months
tempInd = indMeInv;
indNoReb = sum(tempInd,2) == 0;
tempInd(indNoReb, :) = nan;
tempInd = FillMonths(tempInd);

% Inialize the weights matrix & store a couple of constants
wMeInv = nan(size(ret));

% Loop over the portfolios
for i = 1:nPtf
    % Calculate the weights based on the market cap for this portfolio
    tempMe = me;
    tempMe(tempInd ~= i) = nan;
    sumTempMe = sum(tempMe, 2, 'omitnan');
    rptdTempMe = repmat(sumTempMe, 1, nStocks);
    tempW = tempMe ./ rptdTempMe;
    wMeInv(tempInd==i) = tempW(tempInd==i);
end


%UMD
indMeMom = makeBivSortInd(me, 2, ...
                          R, [30 70], ...
                          'sortType', 'unconditional', ...
                          'breaksFilterInd', NYSE);

% Inialize the weights matrix & store a couple of constants
wMeMom = nan(size(ret));

% Loop over the portfolios
for i = 1:nPtf
    % Calculate the weights based on the market cap for this portfolio
    tempMe = me;
    tempMe(indMeMom ~= i) = nan;
    sumTempMe = sum(tempMe, 2, 'omitnan');
    rptdTempMe = repmat(sumTempMe, 1, nStocks);
    tempW = tempMe ./ rptdTempMe;
    wMeMom(indMeMom==i) = tempW(indMeMom==i);
end

% Create the long/short portfolio indices for the three factors (1=short; 2=long)
indSMB = 1 * ismember(indFF93,     [4:6]) + 2 * ismember(indFF93,     [1:3]);
indHML = 1 * ismember(indFF93,     [1 4]) + 2 * ismember(indFF93,     [3 6]);
indRMW = 1 * ismember(indMEOpProf, [1 4]) + 2 * ismember(indMEOpProf, [3 6]);
indCMA = 1 * ismember(indMeInv,    [1 4]) + 2 * ismember(indMeInv,    [3 6]);
indUMD = 1 * ismember(indMeMom,    [1 4]) + 2 * ismember(indMeMom,    [3 6]);

% Calculate the tcosts; Use adjusted w (see Equations (XXX) and (XXX) in 
% DNMV Appendix)
[smb_ptf_tc, smb_TO] = calcTcosts(tcosts, indSMB, me, 'weighting', wFF93/3);
[hml_ptf_tc, hml_TO] = calcTcosts(tcosts, indHML, me, 'weighting', wFF93/2);
[rmw_ptf_tc, rmw_TO] = calcTcosts(tcosts, indRMW, me, 'weighting', wMeOpProf/2);
[cma_ptf_tc, cma_TO] = calcTcosts(tcosts, indCMA, me, 'weighting', wMeInv/2);
[umd_ptf_tc, umd_TO] = calcTcosts(tcosts, indUMD, me, 'weighting', wMeMom/2);

% Add the long and short portfolio trading costs, assume zero costs for MKT
mkt_tc = zeros(size(dates));
smb_tc = sum(smb_ptf_tc, 2);
hml_tc = sum(hml_ptf_tc, 2);
rmw_tc = sum(rmw_ptf_tc, 2);
cma_tc = sum(cma_ptf_tc, 2);
umd_tc = sum(umd_ptf_tc, 2);

% Replicate the factors
% Replicate the factors using the adjusted weights matrix w 
resSMB = runUnivSort(ret, indSMB, dates, wFF93/3,     'weighting', 'v', ...
                                                      'factorModel', 1, ...
                                                      'printResults', 0, ...
                                                      'plotFigure', 0);
resHML = runUnivSort(ret, indHML, dates, wFF93/2,     'weighting', 'v', ...
                                                      'factorModel', 1, ...
                                                      'printResults', 0, ...
                                                      'plotFigure', 0);
resRMW = runUnivSort(ret, indRMW, dates, wMeOpProf/2, 'weighting', 'v', ...
                                                      'factorModel', 1, ...
                                                      'printResults', 0, ...
                                                      'plotFigure', 0);
resCMA = runUnivSort(ret, indCMA, dates, wMeInv/2,    'weighting', 'v', ...
                                                      'factorModel', 1, ...
                                                      'printResults', 0, ...
                                                      'plotFigure', 0);
resUMD = runUnivSort(ret, indUMD, dates, wMeMom/2,    'weighting', 'v', ...
                                                      'factorModel', 1, ...
                                                      'printResults', 0, ...
                                                      'plotFigure', 0);

% Store them in the replication vectors
smb_rep = resSMB.pret(:, end);
hml_rep = resHML.pret(:, end); 
rmw_rep = resRMW.pret(:, end);
cma_rep = resCMA.pret(:, end);
umd_rep = resUMD.pret(:, end);


% Check the replication quality (should see >95% R2)
prt(nanols(smb, [const smb_rep]))
prt(nanols(hml, [const hml_rep]))
prt(nanols(rmw, [const rmw_rep]))
prt(nanols(cma, [const cma_rep]))
prt(nanols(umd, [const umd_rep]))

% Create the factor model tcost matrices
ff3_tc = [mkt_tc smb_tc hml_tc];
ff4_tc = [ff3 umd_tc];
ff5_tc = [ff3_tc rmw_tc cma_tc];
ff6_tc = [ff5_tc umd_tc];

% Save the replicated factors, tcosts, and dWs in the /Data/ folder
save data/ff_rep mkt smb_rep hml_rep rmw_rep cma_rep umd_rep
save data/ff_tc mkt_tc hml_tc smb_tc rmw_tc cma_tc umd_tc  hml_TO smb_TO rmw_TO cma_TO umd_TO ff3_tc ff4_tc ff5_tc ff6_tc

