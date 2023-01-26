function Res = estFactorRegs(pret,dates,factorModel,varargin) 
% PURPOSE: Calculates factor model regressions
%------------------------------------------------------------------------------------------
% USAGE:      
%      Res = estFactorRegs(pret,dates,factorModel,varargin)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -pret - a matrix of portfolio returns                                  
%        -dates - dates vector   
%        -'factorModel' - factor model, which can be user-defined matrix or:
%                         1: CAPM 
%                         3: FF3 factor 
%                         4: FF4 factor (default)
%                         5: FF5 factor 
%                         6: FF6 factor 
% Optional Name-Value Pair Arguments:
%        -'addLongShort' - flag equal to 0 or 1 (default) indicating whether to add a long/short portfolio
%        -'inputIsExcessReturn' - flag equal to 1 or 0 (default) indicator whether the input is excess return
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
%------------------------------------------------------------------------------------------
% Examples:
%
% estFactorRegs(pret,dates,6,1); % FF6 factor-model regression results, including long/short portfolio
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

p=inputParser;
validNum=@(x) isnumeric(x);
validScalarNum=@(x) isnumeric(x) && isscalar(x);
addRequired(p,'pret',validNum);
addRequired(p,'dates',validNum);
addRequired(p,'factorModel',validNum);
addOptional(p,'addLongShort',1,validScalarNum);
addOptional(p,'inputIsExcessRets',0,validScalarNum);
parse(p,pret,dates,factorModel,varargin{:});


% Check if daily dates
datesLength=length(num2str(dates(1)));
switch datesLength
    case 6 % monthly
        load ff
    case 8 % daily
        load dff
        rf=drf;
        ffdates=dffdates;
        mkt=dmkt;
        smb=dsmb;
        smb2=dsmb2;
        hml=dhml;
        umd=dumd;
        cma=dcma;
        rmw=drmw;                
    otherwise
        error('Unknown dates format for factor regressions.');    
end

% Adjust the size of the risk-free rate vector (rf) if necessary
[~,~,indDates]=intersect(dates,ffdates);
rf = rf(indDates);

% Choose the factors
const=ones(size(dates));
if length(factorModel)==1 % Means one of the FF ones
    switch factorModel
        case 1
            heads={'mkt'}; % CAPM           
            x=[const mkt(indDates)]; % CAPM           
        case 3
            heads={'mkt','smb','hml'}; % FF3
            x=[const mkt(indDates) smb(indDates) hml(indDates)]; % FF3
        case 4
            heads={'mkt','smb','hml','umd'}; % FF4
            x=[const mkt(indDates) smb(indDates) hml(indDates) umd(indDates)]; % FF4
        case 5
            heads={'mkt','smb','hml','rmw','cma'}; % FF5
            x=[const mkt(indDates) smb2(indDates) hml(indDates) rmw(indDates) cma(indDates)]; % FF5
        case 6
            heads={'mkt','smb','hml','rmw','cma','umd'}; % FF6
            x=[const mkt(indDates) smb2(indDates) hml(indDates) rmw(indDates) cma(indDates) umd(indDates)]; % FF6
    end
    nFactors=factorModel;
else
    x  = [const factorModel]; % User-defined factor model
    nFactors=size(factorModel,2);
    heads={};
    for i=1:nFactors
        heads=[heads {['reg ',char(num2str(i))]}];
    end    
end


factorLoadings=struct;
for i=1:nFactors
    factorLoadings(i,1).label=heads(i);
    factorLoadings(i,1).factor=x(:,i+1);
end
    
numPtfs=size(pret,2);

% Check is user input excess or raw returns
if p.Results.inputIsExcessRets~=0 % That means input is raw returns
    ptfXRets=pret; 
else    
    ptfXRets=pret-repmat(rf,1,numPtfs);
end

if p.Results.addLongShort~=0    
    longShortPtf=pret(:,end)-pret(:,1);
    pret(:,numPtfs+1)=longShortPtf;
    ptfXRets(:,numPtfs+1)=longShortPtf;
    numPtfs=numPtfs+1;
end

resid=nan(size(pret));

for i=1:(numPtfs)
    
    y=ptfXRets(:,i);
    resx = nanols(y,x);
    
    indFinite=isfinite(sum([y x],2));
    if sum(indFinite)>0
        alpha(i,1) = resx.beta(1)*100;
        talpha(i,1) = resx.tstat(1);

        sharpe(i,1) = sqrt(12)*nanmean(y)/nanstd(y); 
        info(i,1) = sqrt(12)*alpha(i)/(100*sqrt(resx.sige));

        R2(i,1) = resx.rbar;

        for k=1:nFactors
            factorLoadings(k,1).b(i,1)=resx.beta(k+1);
            factorLoadings(k,1).t(i,1)=resx.tstat(k+1);        
        end

        resid(indFinite,i)=resx.resid;

        resc = nanols(y,ones(size(y)));
        xret(i,1) = resc.beta*100;
        txret(i,1) = resc.tstat;
    end
end

Res = struct;

Res.xret = xret;
Res.txret = txret;

Res.alpha = alpha;
Res.talpha = talpha;

Res.sharpe = sharpe;
Res.info = info;
 
Res.pret = pret;                                       % Add the long-short portfolio time-series to pret

Res.factorModel = factorModel;
Res.nFactors = nFactors;
Res.factorLoadings = factorLoadings;
Res.r2 = R2;
Res.resid = resid;

