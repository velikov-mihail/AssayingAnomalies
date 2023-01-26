function results = runFamaMacBeth(y,x,dates,varargin)
% PURPOSE: Estimates Fama-MacBeth cross-sectional regressions of y on x
%------------------------------------------------------------------------------------------
% USAGE: 
%       results = runFamaMacBeth(y, x, dates);                   
%       results = runFamaMacBeth(y, x, dates, Name, Value);      
%------------------------------------------------------------------------------------------
% Required Inputs:
%       -y - matrix with LHS variable (usually 100*ret)        
%       -x - a matrix with concatenated RHS variables
%       -dates - a vector of dates
% Optional Name-Value Pair Arguments:
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
%         runFamaMacBeth(100*ret,[log(me) R],dates);
%         runFamaMacBeth(100*ret,[log(me) R],dates,'minObs',1000);
%         runFamaMacBeth(100*ret,[log(me) R],dates,'weightMatrix',me);
%         runFamaMacBeth(100*ret,[log(me) R],dates,'neweyWestLags',12);
%         runFamaMacBeth(100*ret,[log(me) R],dates,'timePeriod',196307);
%         runFamaMacBeth(100*ret,[log(me) R],dates,'timePeriod',[192807 196306]);
%         runFamaMacBeth(100*ret,[log(me) R],dates,'winsorTrimPctg',5);
%         runFamaMacBeth(100*ret,[log(me) R],dates,'noConst',1);
%         runFamaMacBeth(100*ret,[log(me) log(bm) R],dates);
%         runFamaMacBeth(100*ret,[log(me) log(bm) R],dates,'keepWarnings',1);
%         runFamaMacBeth(100*ret,[log(me) log(bm) R],dates,'labels',{'Const','log(me)','log(bm)','R'});
%------------------------------------------------------------------------------------------
% Dependencies:
%       None.
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

% Parse the inputs
p=inputParser;
validNum=@(x) isnumeric(x);
validScalarNum=@(x) isnumeric(x) && isscalar(x);
validWinsorTrimPctg=@(x) isnumeric(x) && isscalar(x) && x>=0 && x<50;
validTrimIndicator=@(x) (x==0) || (x==1);
validStartingDatesInput=@(x) isnumeric(x) && sum(ismember(dates,x))==length(x);
validCell=@(x) iscell(x);
addRequired(p,'x',validNum);
addRequired(p,'dates',validNum);
addOptional(p,'timePeriod',[dates(1) dates(end)],validStartingDatesInput);
addOptional(p,'trimIndicator',0,validTrimIndicator);
addOptional(p,'winsorTrimPctg',1,validWinsorTrimPctg);
addOptional(p,'printResults',1,validScalarNum);
addOptional(p,'weightMatrix',ones(size(y)),validNum);
addOptional(p,'minObs',100,validScalarNum);
addOptional(p,'neweyWestLags',0,validScalarNum);
addOptional(p,'noConst',0,validScalarNum);
addOptional(p,'keepWarnings',0,validScalarNum);
addOptional(p,'labels',{},validCell);
parse(p,y,x,dates,varargin{:});

if p.Results.keepWarnings==0
    warning off;
else
    warning on;
end

% Get the number of regressors
[T,N] = size(y);
[Tx,Nx] = size(x);
k = Nx / N;
if round(k)~=k || Tx~=T
    error('Check the number of regressors or dimensions of y and x.');
end

% Check if weighted least squares
weightMatrix=p.Results.weightMatrix; 
if size(weightMatrix,1)~=T || size(weightMatrix,2)~=N
    error('Wrong dimensions of weight matrix.');
else
    if isequal(weightMatrix,ones(size(y)))
        wlsIndicator=false;
    else
        if sum(sum(weightMatrix<0))>0
            error('Weight matrix has to be positive.');
        end
        wlsIndicator=true;
        weightMatrix=lag(weightMatrix,1,nan);        
    end
end

% Winsorize, fill in, and lag the RHS variables
for i=1:k
    % Take the current x
    colsCurrentX=(i-1)*N+1 : (i*N);
    thisX=x(:,colsCurrentX);
    thisX(~isfinite(thisX) | imag(thisX))=nan;
    
    % Winsorize if need be
    if p.Results.winsorTrimPctg>0
        if p.Results.trimIndicator==1
            thisX=trim(thisX,p.Results.winsorTrimPctg);
        else
            thisX=winsorize(thisX,p.Results.winsorTrimPctg);
        end
    end
    
    % Fill it in if need be
    indFinite=find(sum(isfinite(thisX),2)>0);
    for j=1:length(indFinite)-1
        thisX(indFinite(j):indFinite(j+1)-1,:)=repmat(thisX(indFinite(j),:),indFinite(j+1)-indFinite(j),1);
    end
    thisX(indFinite(end):T,:)=repmat(thisX(indFinite(end),:),T-indFinite(end)+1,1);
    
    % Lag it 
    x(:,colsCurrentX)=lag(thisX,1,nan);
end

% Check if different time period entered
if ~isequal(p.Results.timePeriod, [dates(1) dates(end)])
    s = find(dates>=p.Results.timePeriod(1),1,'first');
    if length(p.Results.timePeriod)==2
        e = find(dates<=p.Results.timePeriod(2),1,'last');
    else
        e = length(dates);
    end
    
    y = y(s:e,:);
    x = x(s:e,:);
    dates = dates(s:e);
    weightMatrix=weightMatrix(s:e,:);
        
end    

% Get rid of rows where no x & y
ind=sum(isfinite(y),2)>0 & sum(isfinite(x),2)>0;
y=y(ind,:);
x=x(ind,:);
weightMatrix=weightMatrix(ind,:);

T=size(y,1);

% Initiate outputs
Rbar2 = nan(T,1);
if p.Results.noConst~=0 % If no constant
    beta = nan(T,k);
    for t = 1:T

        y_t = y(t,:)';
        x_t = x(t,:)';
        x_t = reshape(x_t,N,k);
        w_t = weightMatrix(t,:)';
        
        nobs=sum(isfinite(sum([y_t x_t w_t],2)));
                    
        if nobs>=p.Results.minObs %at least 100 obs                
            if wlsIndicator
                w_t=w_t/nansum(w_t);                
                res= nanwls(y_t,x_t,w_t);
            else
                res = nanols(y_t,x_t);
            end
            beta(t,1:k)  = res.beta';
            Rbar2(t)  = res.rbar;
        end
    end           
else % add a constant
    beta=nan(T,k+1);
    for t = 1:T


        y_t = y(t,:)';
        x_t = x(t,:)';
        x_t = reshape(x_t,N,k);
        w_t = weightMatrix(t,:)';

        nobs=sum(isfinite(sum([y_t x_t w_t],2)));
        
        if nobs >= p.Results.minObs %at least 100 obs
            x_t = [ones(size(x_t,1),1) x_t];
            if wlsIndicator
                w_t=w_t/nansum(w_t);
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

%need all 3 estimates ;
% beta(isnan(sum(beta,2)),:) = nan ;

if p.Results.neweyWestLags>0 % Run Newey-West

    indFinite=isfinite(sum(beta,2));
    for i= 1:size(beta,2)    
        res = nwest(beta(indFinite,i),ones(size(beta(indFinite,i))),p.Results.neweyWestLags);
        bhat(i) = res.beta;
        t(i) = res.tstat;
    end
else % Run OLS
    indFinite=isfinite(sum(beta,2));
    for i= 1:size(beta,2)    
        res = nanols(beta(indFinite,i),ones(size(beta(indFinite,i))));
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
results.mean_R2 = nanmean(Rbar2);


if p.Results.printResults~=0
    in.rnames='';
    if ~isempty(p.Results.labels)        
        nchar=max(cellfun(@(x) length(char(x)),p.Results.labels));
        for i=1:length(p.Results.labels)
            clabel=char(p.Results.labels(i));
            nclabel=length(clabel);
            in.rnames=strvcat(in.rnames,[blanks(25-nclabel-(nchar-nclabel+1)),clabel,blanks(nchar-nclabel+1)]);
        end
    else
        for i=1:k
            in.rnames = strvcat(in.rnames,['                    var ' int2str(i)]) ;
        end
        
        if p.Results.noConst==0     % If we have a  constant
            in.rnames =[ ['                    var 0']; ...
                            in.rnames];
        end
    end
    in.rnames = [blanks(25); in.rnames];
    in.fmt=strvcat('%12.3f');

    fprintf('---------------------------------------------------------------------- \n')
    fprintf('           Results from Fama - MacBeth regressions \n')
    fprintf('---------------------------------------------------------------------- \n')
    m = [bhat' t'];
    in.cnames = strvcat('Coeff','t-stat');
    mprint(m,in)
    fprintf('---------------------------------------------------------------------- \n')
end



if p.Results.keepWarnings==0
    warning on;
end

