function Res = runUnivSort(ret,ind,dates,mcap,varargin)
% PURPOSE: This function runs a univariate sort and calculates portfolio
% average returns and estimates alphas and loadings on a factor model
%------------------------------------------------------------------------------------------
% USAGE:   
% Res = runUnivSort(ret,ind,dates,me);              % 4 required arguments.                                 
% Res = runUnivSort(ret,ind,dates,me,Name,Value);   % Allows you to specify optional inputs
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -ret - a matrix of stock returns                                  
%        -ind - a matrix indicating portfolio holdings                  
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
%        -'addLongShort' - flag equal to 0 or 1 (default) indicating whether to add a long/short portfolio
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
%         -Res.loadings - a structure with factors, loadings, t-statistics, and labels
%         -Res.r2 - a vector of adjusted R-squared's from factor model regressions
%         -Res.resid - a matrix of residuals from factor model regressions (reduced size)
%         -Res.dates - a vector of dates corresponding to the pret output
%         -Res.hperiod - a scalar indicating the holding period
%         -Res.w - a character indicating portfolio weighting scheme ('V' or 'E')
%         -Res.nStocks - a matrix with time-series of # of stocks in each portfolio 
%         -Res.ptfMarketcap - a matrix with time-series of market cap for each portfolio 
%------------------------------------------------------------------------------------------
% Examples:
%
% Res = runUnivSort(ret,ind,dates,me);                              % 4 required arguments.                                 
% Res = runUnivSort(ret,ind,dates,me,'weighting','e');              % Equal-weighting
% Res = runUnivSort(ret,ind,dates,me,'tcosts',tcosts);              % Calculate tcosts
% Res = runUnivSort(ret,ind,dates,me,'holdingPeriod',2);            % 2-month holding per.
% Res = runUnivSort(ret,ind,dates,me,'factorModel',6);              % 6-factor model
% Res = runUnivSort(ret,ind,dates,me,'factorModel',ff6(:,2:end));   % User defined model. 
% Res = runUnivSort(ret,ind,dates,me,'printResults',0);             % Don't print results
% Res = runUnivSort(ret,ind,dates,me,'plotFigure',0);               % Don't plot figure
% Res = runUnivSort(ret,ind,dates,me,'timePeriod',196307);          % Start in 196307
% Res = runUnivSort(ret,ind,dates,me,'timePeriod',[192601 196306]); % Use 192601-196306 
% Res = runUnivSort(ret,ind,dates,me,'factorModel',4, ...
%                                    'weighting','v', ...
%                                    'timePeriod',[192512], ...
%                                    'holdingPeriod',2);            % Order doesn't matter
% Res = runUnivSort(ret,ind,dates,me,'weighting','v', ...
%                                    'holdingPeriod',1, ...
%                                    'factorModel',4, ...
%                                    'printResults',1, ...
%                                    'plotFigure',0, ...
%                                    'timePeriod',[192512], ...
%                                    'addLongShort',1);             % Specify all  inputs
% Res = runUnivSort(ret,ind,dates,me,'v',1,4,1,0,[192512]);         % W/o specifying 'Name' 
% Res = runUnivSort(ret,ind,dates,me,'v',1,5);                      % Only partial inputs
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses calcPtfRets(), estFactorRegs(), prtSortResults(), plotStrategyFigs(), TCE_sub()
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

% Parse the inputs
expectedWeighting={'V','v','E','e'};

p=inputParser;
validNum=@(x) isnumeric(x);
validScalarNum=@(x) isnumeric(x) && isscalar(x);
validStartingDatesInput=@(x) isnumeric(x) && sum(ismember(dates,x))==length(x);
addRequired(p,'ret',validNum);
addRequired(p,'ind',validNum);
addRequired(p,'dates',validStartingDatesInput);
addRequired(p,'mcap',validNum);
addOptional(p,'weighting','v',@(x) any(validatestring(x,expectedWeighting)));
addOptional(p,'holdingPeriod',1,validScalarNum);
addOptional(p,'factorModel',4,validNum);
addOptional(p,'printResults',1,validScalarNum);
addOptional(p,'plotFigure',1,validScalarNum);
addOptional(p,'timePeriod',[dates(1) dates(end)],validStartingDatesInput);
addOptional(p,'addLongShort',1,validScalarNum);
addOptional(p,'tcosts',-99,validNum);
parse(p,ret,ind,dates,mcap,varargin{:});

% Check whether the dimensions are correct
if ~isequal(size(mcap), size(ret)) || ...
   ~isequal(size(ind), size(ret)) || ...
   size(dates,1) ~= size(ret,1) 
    error('Check ret, ind, mcap, and dates - they have different dimensions.');
end

% Check the factor model code (if entered) is correct
if length(p.Results.factorModel) == 1
    if ~ismember(p.Results.factorModel,[1 3 4 5 6])
        error('Factor model must be 1, 3, 4, 5, 6, or a user-defined matrix.');
    end
end

% Check if user entered a subsample
if ~isequal(p.Results.timePeriod, [dates(1) dates(end)])
    s = find(dates>=p.Results.timePeriod(1),1,'first');
    if length(p.Results.timePeriod)==2
        e = find(dates<=p.Results.timePeriod(2),1,'last');
    else
        e = length(dates);
    end
    
    ret = ret(s:e,:);
    ind = ind(s:e,:);
    dates = dates(s:e);
    mcap = mcap(s:e,:);

end    

% Delete all stocks (i.e., columns) that are not held in any portfolio in the full sample
stockIsHeld = (sum(ind,1)>0);
ret(:,~stockIsHeld) = [];
ind(:,~stockIsHeld) = [];
mcap(:,~stockIsHeld)  = [];

% Calculate the ptf returns, # stocks, and market caps
[pret,nStocks,ptfMarketCap] = calcPtfRets(ret,ind,mcap,p.Results.holdingPeriod,lower(p.Results.weighting));     

% Estimate the factor model regressions
Res=estFactorRegs(pret,dates,p.Results.factorModel,p.Results.addLongShort);

% Check if we need to estimate trading costs
if p.Results.tcosts~=-99
    tcosts=p.Results.tcosts;
    if length(tcosts)==1 % If it's just a constant tcost
        tcosts=tcosts*(mcap./mcap);
    else
        tcosts(:,~stockIsHeld) = [];
        if exist('s','Var')
            tcosts=tcosts(s:e,:);
        end
    end
    nPtfs=max(max(ind));
    for i=1:nPtfs
        weightingIndicator=1*strcmp(upper(p.Results.weighting),'V');
        [ptfCosts(:,i),ptfTO(:,i)] = TCE_sub(ret,ind,tcosts,mcap,weightingIndicator,i);
    end
    Res.tcostsTS = ptfCosts(:,1) + ptfCosts(:,end);
    Res.toTS = [ptfTO(:,1) ptfTO(:,end)];
    Res.netpret=Res.pret(:,end)-Res.tcostsTS;
    netRes=nanols(100*Res.netpret,ones(size(Res.netpret)));
    Res.netxret=netRes.beta;
    Res.tnetxret=netRes.tstat;
    Res.turnover=mean(nanmean(Res.toTS)/2);
    Res.tcosts=mean(Res.tcostsTS);
    Res.ptfCosts=ptfCosts;
    Res.ptfTO=ptfTO;    
end

% Store a few more variables
Res.dates=dates;
Res.hperiod=p.Results.holdingPeriod;
Res.w=p.Results.weighting;
if p.Results.addLongShort~=0
    Res.nStocks = [nStocks nStocks(:,end)+nStocks(:,1)];                                       % Add the long-short portfolio time-series # of stocks
else 
    Res.nStocks = [nStocks];
end
Res.ptfMarketCap=ptfMarketCap;

% Print the results
if p.Results.printResults~=0 
    prtSortResults(Res,p.Results.addLongShort);
end

% Plot the figure
if p.Results.plotFigure ~= 0 && p.Results.addLongShort ~=0
    figure(83);
    plotStrategyFigs(Res);
end
    


