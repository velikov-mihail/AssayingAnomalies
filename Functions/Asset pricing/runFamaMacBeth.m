function results = runFamaMacBeth(y, x, dates, varargin)
% PURPOSE: Estimates Fama-MacBeth cross-sectional regressions of y on x.
% The function lags the x variables by one period by default, so no need to
% passs lagged values. 
%------------------------------------------------------------------------------------------
% USAGE: 
%       results = runFamaMacBeth(y, x, dates);                   
%       results = runFamaMacBeth(y, x, dates, Name, Value);      
%------------------------------------------------------------------------------------------
% Required Inputs:
%       -y - matrix with LHS variable (usually 100*ret)        
%       -x - a matrix with concatenated RHS variables. By default, the
%            function lags these variables 1 period.
%       -dates - a vector of dates
% Optional Name-Value Pair Arguments:
%        -'numLags' - a number (1 by default) indicating the number of
%                    periods used to lag the x variables
%        -'minObs' - a number (100 by default) of minimum observations
%                    required for each cross-sectional regression
%        -'weightMatrix' - a weighting matrix which is used to estimate
%                       weighted- instead of ordinary- least squares cross-
%                       sectional regressions
%        -'neweyWestLags' - a number indicating the number of lags to use
%                           in the Newey-West procedure for the standard errors. Default is 
%                           0, which indicates using OLS standard errors
%        -'printResults' - flag equal to 0 or 1 (default) indicating whether to print results
%        -'timePeriod' - a scalar or two-by-one vector of dates in YYYYMM format indicating 
%                        sample start or sample range (default is first element in dates)
%        -'trimIndicator' - flag equal to 0 (deafult) or 1 indicating whether to trim
%                           instead of winsorizing the variables
%        -'winsorTrimPctg' - a number indicating the percentage at which to
%                            trim or winsorize the RHS variables (default = 1). If equal to 
%                            0, there is no trimming or winsorization
%        -'noConst' - flag equal to 0 (default) or 1 indicating whether to
%                     include a constant (0) or not (1)
%        -'keepWarnings' - flag equal to 0 (default) or 1 indicating whether to keep warnings
%        -'labels' - a cell array of labels for each of the RHS variables
%------------------------------------------------------------------------------------------
% Output:
%        -Res - a structure containing results for the Fama-MacBeth regressions
%         -Res.beta - time-series of beta coefficients from cross-sectional regressions
%         -Res.bhat - average(s) of Res.beta
%         -Res.t - t-statistic(s) on Res.bhat
%         -Res.Rbar2 - time-series of adjusted R2 from cross-sectional regressions
%         -Res.mean_R2 - average of Res.Rbar2
%------------------------------------------------------------------------------------------
% Examples: 
%         runFamaMacBeth(100*ret, [log(me) R], dates);
%         runFamaMacBeth(100*ret, [lag(log(me),1,nan)], dates, 'numLags', 0);
%         runFamaMacBeth(100*ret, [log(me) R], dates, 'timePeriod', 196307);
%         runFamaMacBeth(100*ret, [log(me) R], dates, 'timePeriod', [192807 196306]);
%         runFamaMacBeth(100*ret, [log(me) R], dates, 'minObs', 1000);
%         runFamaMacBeth(100*ret, [log(me) R], dates, 'weightMatrix', me);
%         runFamaMacBeth(100*ret, [log(me) R], dates, 'neweyWestLags', 12);
%         runFamaMacBeth(100*ret, [log(me) R], dates, 'winsorTrimPctg', 5);
%         runFamaMacBeth(100*ret, [log(me) R], dates, 'noConst', 1);
%         runFamaMacBeth(100*ret, [log(me) log(bm) R], dates);
%         runFamaMacBeth(100*ret, [log(me) log(bm) R], dates, 'keepWarnings', 1);
%         runFamaMacBeth(100*ret, [log(me) log(bm) R], dates, 'labels', {'Const','log(me)','log(bm)','R'});
%------------------------------------------------------------------------------------------
% Dependencies:
%       None.
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Parse the inputs
p = inputParser;
validNum = @(x) isnumeric(x);
validScalarNum = @(x) isnumeric(x) && isscalar(x);
validWinsorTrimPctg = @(x) isnumeric(x) && isscalar(x) && x>=0 && x<50;
validTrimIndicator = @(x) (x==0) || (x==1);
validStartingDatesInput = @(x) isnumeric(x) && sum(ismember(dates,x))==length(x);
validCell = @(x) iscell(x);
addRequired(p, 'y', validNum);
addRequired(p, 'x', validNum);
addRequired(p, 'dates', validNum);
addOptional(p, 'numLags', 1, validNum);
addOptional(p, 'timePeriod', [dates(1) dates(end)], validStartingDatesInput);
addOptional(p, 'minObs', 100, validScalarNum);
addOptional(p, 'weightMatrix', ones(size(y)), validNum);
addOptional(p, 'trimIndicator', 0, validTrimIndicator);
addOptional(p, 'winsorTrimPctg', 1, validWinsorTrimPctg);
addOptional(p, 'printResults', 1, validScalarNum);
addOptional(p, 'neweyWestLags', 0, validScalarNum);
addOptional(p, 'noConst', 0, validScalarNum);
addOptional(p, 'keepWarnings', 0, validScalarNum);
addOptional(p, 'labels', {}, validCell);
parse(p, y, x, dates, varargin{:});

if p.Results.keepWarnings==0
    warning off;
else
    warning on;
end

% Get the number of regressors
[nDates, nStocks] = size(y);
[nDatesX, nObsXMatrix] = size(x);
nX = nObsXMatrix / nStocks;
if round(nX)~=nX || nDatesX~=nDates
    error('Check the number of regressors or dimensions of y and x.');
end

% Check if weighted least squares
weightMatrix = p.Results.weightMatrix; 
if size(weightMatrix,1)~=nDates || size(weightMatrix,2)~=nStocks
    error('Wrong dimensions of weight matrix.');
else
    if isequal(weightMatrix,ones(size(y)))
        wlsIndicator = false;
    else
        if sum(sum(weightMatrix<0))>0
            error('Weight matrix has to be positive.');
        end
        wlsIndicator = true;
        weightMatrix = lag(weightMatrix,1,nan);        
    end
end

% Winsorize, fill in, and lag the RHS variables
for i=1:nX
    % Take the current x
    colsCurrentX = (i-1)*nStocks+1 : (i*nStocks);
    thisX = x(:,colsCurrentX);
    thisX(~isfinite(thisX) | imag(thisX)) = nan;
    
    % Winsorize if need be
    if p.Results.winsorTrimPctg>0
        if p.Results.trimIndicator==1
            thisX = trim(thisX,p.Results.winsorTrimPctg);
        else
            thisX = winsorize(thisX,p.Results.winsorTrimPctg);
        end
    end
    
    % Fill it in if need be
    indRowsWithData = find(sum(isfinite(thisX),2)>0);
    dataFreq = mode(indRowsWithData-lag(indRowsWithData, 1, nan));
    if dataFreq>1
        for j=1:length(indRowsWithData)-1
            b = indRowsWithData(j);
            e = indRowsWithData(j+1);
            thisX(b:e-1,:) = repmat(thisX(b,:), e-b, 1);
        end
        thisX(indRowsWithData(end):nDates,:) = repmat(thisX(indRowsWithData(end),:),nDates-indRowsWithData(end)+1,1);
    end
    
    % Lag it 
    if p.Results.numLags > 0
        x(:,colsCurrentX) = lag(thisX, p.Results.numLags, nan);
    end
end

% Check if different time period entered
if ~isequal(p.Results.timePeriod, [dates(1) dates(end)])
    % Figure out the common sample    
    s = find(dates>=p.Results.timePeriod(1), 1, 'first');
    if length(p.Results.timePeriod)==2
        e = find(dates<=p.Results.timePeriod(2), 1, 'last');
    else
        e = length(dates);
    end
    
    % Subset
    y = y(s:e,:);
    x = x(s:e,:);
    dates = dates(s:e);
    weightMatrix = weightMatrix(s:e,:);
        
end    

% Get rid of rows where no x & y
ind = sum(isfinite(y),2)>0 & sum(isfinite(x),2)>0;
y = y(ind,:);
x = x(ind,:);
weightMatrix = weightMatrix(ind,:);

% Store the number of dates
nDates = size(y,1);

% Initiate outputs
Rbar2 = nan(nDates,1);

% If no constant
if p.Results.noConst~=0 
    beta = nan(nDates, nX);
    for t = 1:nDates
        
        % Subset for this month
        y_t = y(t,:)';
        x_t = x(t,:)';
        x_t = reshape(x_t, nStocks, nX);
        w_t = weightMatrix(t,:)';
        
        % Check the min observations
        nObs = sum(isfinite(sum([y_t x_t w_t], 2)));                    
        if nObs>=p.Results.minObs            
            if wlsIndicator
                w_t = w_t/sum(w_t, 'omitnan');                
                res = nanwls(y_t, x_t, w_t);
            else
                res = nanols(y_t, x_t);
            end
            beta(t,1:nX)  = res.beta';
            Rbar2(t)  = res.rbar;
        end
    end           
else 
    % Add a constant
    beta = nan(nDates,nX+1);
    const = ones(nStocks, 1);
    for t = 1:nDates


        y_t = y(t,:)';
        x_t = x(t,:)';
        x_t = [const reshape(x_t, nStocks, nX)];
        w_t = weightMatrix(t,:)';

        % Check the min observations
        nObs = sum(isfinite(sum([y_t x_t w_t], 2)));        
        if nObs >= p.Results.minObs 
            if wlsIndicator
                w_t = w_t/sum(w_t, 'omitnan');
                res= nanwls(y_t,x_t,w_t);
            else
                res = nanols(y_t,x_t);
            end
            beta(t,:) = res.beta';
            Rbar2(t) = res.rbar;
        end
    end
end

% --------------- Average the cross sectional regressions  --------------------------- %

% Initialize the beta and t-stat vectors
bhat = nan(1, size(beta, 2));
t = nan(1, size(beta, 2));

indFinite = isfinite(sum(beta, 2));
x = ones(sum(indFinite),1);

if p.Results.neweyWestLags>0 
    % Run Newey-West
    for i= 1:size(beta,2)    
        y = beta(indFinite,i);        
        res = nwest(y, x, p.Results.neweyWestLags);
        bhat(i) = res.beta;
        t(i) = res.tstat;
    end
else 
    % Run OLS
    for i= 1:size(beta,2)    
        y = beta(indFinite,i);        
        res = nanols(y, x);
        bhat(i) = res.beta;
        t(i) = res.tstat;
    end
end

% ------------ store results -------------------------------- %
results.dates = dates;
results.beta = beta;
results.bhat = bhat;
results.t = t;
results.Rbar2 = Rbar2;
results.mean_R2 = mean(Rbar2, 'omitnan');

% Print
if p.Results.printResults~=0
    prtFMBResults(p, bhat, t)
end

% Keep warnings
if p.Results.keepWarnings==0
    warning on;
end

