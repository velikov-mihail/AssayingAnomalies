function [Res, CondRes] = runBivSort(ret, ind, nPtf1, nPtf2, dates, mcap, varargin)
% PURPOSE: This function runs a univariate sort and calculates portfolio
% average returns and estimates alphas and loadings on a factor model
%------------------------------------------------------------------------------------------
% USAGE:   
% [Res, CondRes] = runBivSort(ret, ind, nPtf1, nPtf2, dates, me);              % 6 required arguments.                                 
% [Res, CondRes] = runBivSort(ret, ind, nPtf1, nPtf2, dates, me, Name, Value); % Allows you to specify optional inputs
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -ret - a matrix of stock returns                                  
%        -ind - a matrix indicating portfolio holdings in the two-way sort                 
%        -nPtf1 - a scalar indicating number of portfolios based on first sort
%        -nPtf2 - a scalar indicating number of portfolios based on second sort
%        -dates - dates vector   
%        -mcap - an optional matrix of market capitalizations (default = 1)   
% Optional Name-Value Pair Arguments:
%        -'weighting' - weighting scheme (one of {'V','v' (default),'E','e'})
%        -'holdingPeriod' - portfolio holding period in months (1=default)
%        -'factorModel' - factor model, which can be user-defined matrix or:
%                         1: CAPM 
%                         3: FF3 factor 
%                         4: FF4 factor (default)
%                         5: FF5 factor 
%                         6: FF6 factor 
%        -'printResults' - flag equal to 0 or 1 (default) indicating whether to print results
%        -'plotFigure' - flag equal to 0 or 1 (default) indicating whether to plot figure
%        -'timePeriod' - a scalar or two-by-one vector of dates in YYYYMM format indicating 
%                        sample start or sample range (default is first element in dates)
%------------------------------------------------------------------------------------------
% Output:
%        -Res - a structure containing results for excess returns and time-series 
%               regressions for the portfolios
%         -Res.xret - a vector of portfolio excess returns
%         -Res.txret - a vector of t-stats on the portfolio excess returns
%         -Res.alpha - a vector of alphas
%         -Res.talpha - a vector of t-stats of the alphas
%         -Res.sharpe - a vector of Sharpe ratios
%         -Res.info - a vector of information ratios
%         -Res.pret - A matrix containing the time-series of portfolio RAW returns
%         -Res.factorModel - a scalar or matrix indicating the factor model used
%         -Res.nFactors - a scalar indicating the number of factors
%         -Res.factorLoadings - a structure with factors, loadings, t-statistics, and labels
%         -Res.r2 - a vector of adjusted R-squared's from factor model regressions
%         -Res.resid - a matrix of residuals from factor model regressions (reduced size)
%         -Res.dates - a vector of dates corresponding to the pret output
%         -Res.hperiod - a scalar indicating the holding period
%         -Res.w - a character indicating portfolio weighting scheme ('V' or 'E')
%         -Res.ptfNumStocks - a matrix with time-series of # of stocks in each portfolio 
%         -Res.ptfMarketcap - a matrix with time-series of market cap for each portfolio 
%         -Res.grsFstat - GRS F-statistic 
%         -Res.grsPval - p-value associated with GRS F-statistic
%         -Res.grsDoF - Degrees of freedom used in GRS test
%        -CondRes - a two-by-one structure containing results for excess returns and 
%                   time-series regressions for long/short portfolios of the conditional 
%                   strategies
%         -CondRes.xret - a vector of portfolio excess returns
%         -CondRes.txret - a vector of t-stats on the portfolio excess returns
%         -CondRes.alpha - a vector of alphas
%         -CondRes.talpha - a vector of t-stats of the alphas
%         -CondRes.sharpe - a vector of Sharpe ratios
%         -CondRes.info - a vector of information ratios
%         -CondRes.pret - A matrix containing the time-series of portfolio RAW returns
%         -CondRes.factorModel - a scalar or matrix indicating the factor model used
%         -CondRes.nFactors - a scalar indicating the number of factors
%         -CondRes.factorLoadings - a structure with factors, loadings, t-statistics, and labels
%         -CondRes.r2 - a vector of adjusted R-squared's from factor model regressions
%         -CondRes.resid - a matrix of residuals from factor model regressions (reduced size)
%         -CondRes.w - a character indicating portfolio weighting scheme ('V' or 'E')
%         -CondRes.hperiod - a scalar indicating the holding period
%------------------------------------------------------------------------------------------
% Examples:
%
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me);                              % 4 required arguments.                                 
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'weighting','e');              % Equal-weighting
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'holdingPeriod',2);            % 2-month holding per.
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'factorModel',6);              % 6-factor model
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'factorModel',ff6(:,2:end));   % User defined model. 
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'printResults',0);             % Don't print results
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'plotFigure',0);               % Don't plot figure
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'timePeriod',196307);          % Start in 196307
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'timePeriod',[192601 196306]); % Use 192601-196306 
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'factorModel',4, ...
%                                    'weighting','v', ...
%                                    'timePeriod',[192512], ...
%                                    'holdingPeriod',2);                          % Order doesn't matter
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'weighting','v', ...
%                                    'holdingPeriod',1, ...
%                                    'factorModel',4, ...
%                                    'printResults',1, ...
%                                    'plotFigure',0, ...
%                                    'timePeriod',[192512], ...
%                                    'addLongShort',1);                           % Specify all  inputs
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'v',1,4,1,0,[192512]);         % W/o specifying 'Name' 
% [Res, CondRes] = runBivSort(ret,ind,5,5,dates,me,'v',1,5);                      % Only partial inputs
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses runUnivSort(), GRStest_p(), estFactorRegs(), prtSortResults().
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.


% Parse the inputs
expectedWeighting = {'V','v','E','e'};

p = inputParser;
validNum = @(x) isnumeric(x);
validScalarNum = @(x) isnumeric(x) && isscalar(x);
validStartingDatesInput = @(x) isnumeric(x) && sum(ismember(dates,x))==length(x);
validWeighting = @(x) any(validatestring(x,expectedWeighting));
addRequired(p, 'ret',  validNum);
addRequired(p, 'ind', validNum);
addRequired(p, 'nPtf1', validScalarNum);
addRequired(p, 'nPtf2', validScalarNum);
addRequired(p, 'dates', validStartingDatesInput);
addRequired(p, 'mcap', validNum);
addOptional(p, 'weighting','v', validWeighting);
addOptional(p, 'holdingPeriod', 1, validScalarNum);
addOptional(p, 'factorModel', 4, validNum);
addOptional(p, 'printResults', 1, validScalarNum);
addOptional(p, 'plotFigure', 0, validScalarNum);
addOptional(p, 'timePeriod', [dates(1) dates(end)], validStartingDatesInput);
parse(p, ret, ind, nPtf1, nPtf2, dates, mcap, varargin{:});

% Run a univariate sort to get the underlying portfolios
Res = runUnivSort(ret, ind, dates, mcap, 'weighting', p.Results.weighting, ...
                                         'holdingPeriod', p.Results.holdingPeriod, ...
                                         'factorModel', p.Results.factorModel, ...
                                         'printResults', p.Results.printResults, ... 
                                         'plotFigure', p.Results.plotFigure, ...
                                         'timePeriod', p.Results.timePeriod, ...
                                         'addLongShort', 0); % Specify all optional inputs

% Add the GRS test results
[Res.grsPval, Res.grsFstat, Res.grsDoF] = GRStest_p(Res);

% Example of what the ind looks like for conditional strategies 
% from a 2x3 sort (nPtf1=2; nPtf2=3):
%        1 2 3
%
%   1    1 2 3
%   2    4 5 6


% Store a few constants
nMonths = length(Res.dates);

% Conditional strategies: High minus low var 1, conditioned on var 2
% These are the (4-1), (5-2), and (6-3) strategies in the example above
longShortCondStrats = nan(nMonths, nPtf2);
for i=1:nPtf2
    thisLongInd = (nPtf1-1)*nPtf2 + i;
    thisShortInd = i;
    longShortCondStrats(:,i) = Res.pret(:,thisLongInd) - Res.pret(:,thisShortInd);
end
CondRes = estFactorRegs(longShortCondStrats, Res.dates, p.Results.factorModel, 'addLongShort', 0, ...
                                                                               'inputIsExcessRets',1);

% Conditional strategies: High minus low var 2, conditioned on var 1
% These are the (3-1) and (6-4) strategies in the example above
longShortCondStrats = nan(nMonths, nPtf1);
for i=1:nPtf1
    thisLongInd = (i-1)*nPtf2 + nPtf2;
    thisShortInd = (i-1)*nPtf2 + 1;
    longShortCondStrats(:,i) = Res.pret(:,thisLongInd) - Res.pret(:,thisShortInd);
end
CondRes(2,1) = estFactorRegs(longShortCondStrats, Res.dates, p.Results.factorModel, 'addLongShort', 0, ...
                                                                                    'inputIsExcessRets',1);

% Do we need GRS test for the conditional strategies?
% for i=1:2
%     [condRes(i).grsPval, condRes(i).grsFstat, condRes(i).grsDoF] = GRStest_p(condRes(i));
% end

% Print the results
if p.Results.printResults~=0 
    % Print the GRS results
    grsres1 = [num2str(Res.grsPval(1)), ' ', num2str(Res.grsFstat(1)), '   ', ...
        num2str(round(Res.grsDoF(1,1))), '   ', num2str(round(Res.grsDoF(1,2)))];
    grsres2 = [num2str(Res.grsPval(2)), ' ', num2str(Res.grsFstat(2)), '   ', ...
        num2str(round(Res.grsDoF(2,1))), '   ', num2str(round(Res.grsDoF(2,2)))];
    disp('      GRS test results:  p-value     F-stat  df1  df2'); 
    disp(['      full test -        ', grsres1]);
    disp(['      partial test -     ', grsres2]);
        
    
    % Add a few descriptors to the structure
    temp = repmat(cellstr(p.Results.weighting), 2, 1);
    [CondRes.w] = temp{:};
    temp = repmat(num2cell(p.Results.holdingPeriod),2,1);   
    [CondRes.hperiod] = temp{:};
    
    % Print the conditional strategies
    prtSortResults(CondRes(1),0);    
    prtSortResults(CondRes(2),0);
    
    % Print the average returns, number of firms, and market cap
    disp('Portfolio Average Excess Returns (%/month)');
    disp('     ') ;
    disp(reshape(Res.xret, nPtf2, nPtf1)')
    disp('Portfolio Average Number of Firms');
    disp('     ') ;
    disp(reshape(round(mean(Res.ptfNumStocks, 1, 'omitnan')), nPtf2, nPtf1)')
    disp('Portfolio Average Firm Size ($10^6)');
    disp('     ') ;
    disp(reshape(round(mean(Res.ptfMarketCap./Res.ptfNumStocks, 1, 'omitnan')), nPtf2, nPtf1)')
end
