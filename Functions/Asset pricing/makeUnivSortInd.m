function ind = makeUnivSortInd(var,ptfNumThresh,varargin)
% PURPOSE: Creates a portfolio index matrix for a univariate sort indicating which 
% portfolio each stock-month belongs to
%------------------------------------------------------------------------------------------
% USAGE: 
%       ind = makeUnivSortInd(var, ptfNumThresh);                   
%       ind = makeUnivSortInd(var, ptfNumThresh, Name, Value);      
%------------------------------------------------------------------------------------------
% Required Inputs:
%       -var - matrix with the variable used for sorting        
%       -ptfNumThresh - a scalar or vector used to determine the number of portfolios
% Optional Name-Value Pair Arguments:
%       -breaksFilterInd - an optional indicator matrix to filter the stocks
%                       for the breakpoints determination (e.g., a matrix with ones for
%                       NYSE stocks)
%       -portfolioMassInd - an optional variable that can be used to ensure the portfolio 
%                       have an equal amount of the variable (e.g., market
%                       capitalization matrix for cap-weighting)
%------------------------------------------------------------------------------------------
% Output:
%       -ind -a matrix that indicates the portfolio each stock-month falls under
%------------------------------------------------------------------------------------------
% Examples: 
%       ind = makeUnivSortInd(var,5);                      quintile sort based on name breaks
%       ind = makeUnivSortInd(var,[30 70]);                tertile FF-style sort based on name breaks
%       ind = makeUnivSortInd(var,10,'breaksFilter',NYSE); decile sort based on NYSE breaks
%       ind = makeUnivSortInd(var,5,'portfolioMassInd',me);  quintile sort based on cap-weighted breaks
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses assignToPtf().
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

% Parse the inputs
expectedBreaksType={'name','NYSE','cap'};

p=inputParser;
validNum=@(x) isnumeric(x);
validNumSize=@(x) (islogical(x) || isnumeric(x)) && (isequal(size(var),size(x)) || isequal(x,1));
addRequired(p,'var',validNum);
addRequired(p,'ptfNumThresh',validNum);
addOptional(p,'breaksFilterInd',1,validNumSize);
addOptional(p,'portfolioMassInd',1,validNumSize);
parse(p,var,ptfNumThresh,varargin{:});

var=p.Results.var;
ptfNumThresh=p.Results.ptfNumThresh;
breaksFilterInd=1*p.Results.breaksFilterInd;
portfolioMassInd=p.Results.portfolioMassInd;

% Determine the breakpoints 
if length(ptfNumThresh)>1 % User entered the breakpoints directly
    bpts=ptfNumThresh;
else % User entered the number of portfolios
    bpts = [];
    for i = 1:ptfNumThresh-1 
        bpts = [bpts i*100/ptfNumThresh];
    end
end

if isequal(portfolioMassInd,1)
    breaksFilterInd(breaksFilterInd==0)=nan;
    p=prctile(var.*breaksFilterInd,bpts,2);
    ind = assignToPtf(var,p);    
else
    portfolioMassInd(isnan(var)) = nan; 
        
    % We'll sort on the variable first & calculate the cumulative market cap
    [~, I] = sort(var,2);
    r_ind = (sum(isfinite(var),2)>0);
    tempvar = nan(size(var));
    for i = find(r_ind)'
        temp =  portfolioMassInd(i,I(i,:));
        t_ind = isnan(temp);
        temp(t_ind) = 0;
        temp = cumsum(temp);
        temp = temp/temp(end);
        temp(t_ind) = nan;
        tempvar(i,I(i,:)) = temp; 
    end

    % Assign based on the breakpoints
    bpts=[0 bpts]/100;        

    ind = zeros(size(var));
    for i = bpts
        ind = ind + (tempvar > i);
    end
end


