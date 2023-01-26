function ind = makeBivSortInd(var1, ptfNumThresh1, var2, ptfNumThresh2, varargin)
% PURPOSE: Creates a portfolio index matrix for a bivariate sort indicating which 
% portfolio each stock-month belongs to
%------------------------------------------------------------------------------------------
% USAGE: 
%       ind = makeBivSortInd(var1, ptfNumThresh1, var2, ptfNumThresh2);                   
%       ind = makeBivSortInd(var1, ptfNumThresh1, var2, ptfNumThresh2, Name, Value);      
%------------------------------------------------------------------------------------------
% Required Inputs:
%       -var1 - matrix with first variable used for sorting        
%       -ptfNumThresh1 - a scalar or vector used to determine the number of portfolios in the first direction
%       -var2 - matrix with second variable used for sorting        
%       -ptfNumThresh2 - a scalar or vector used to determine the number of portfolios in the second direction
% Optional Name-Value Pair Arguments:
%       -sortType - an optional string indicating whether bivariate sort is
%                   'unconditional' (default) or 'conditional'
%       -breaksFilterInd - an optional string indicating whether portfolio
%                    breakpoints are based on 'name' (default), 'NYSE', or 'cap'
%------------------------------------------------------------------------------------------
% Output:
%       -ind -a matrix that indicates the portfolio each stock-month falls under
%------------------------------------------------------------------------------------------
% Examples:
%       % 5x5 unconditional sort on size and momentum using name breaks
%       ind = makeBivSortInd(me, 5, R, 5);                                 
%       % 2x3 (FF-style tertiles) unconditional sort on size and momentum using name breaks
%       ind = makeBivSortInd(me, 2, R, [30 70]);                           
%       % 5x5 conditional sort on size and momentum
%       ind = makeBivSortInd(me, 5, R, 5, 'sortType', 'conditional');      
%       % 5x5 unconditional sort on size and momentum using NYSE breaks
%       ind = makeBivSortInd(me, 5, R, 5, 'breaksFilterInd', 'NYSE');      
%       % 5x5 unconditional sort on size and momentum using cap breaks
%       ind = makeBivSortInd(me, 5, R, 5, 'breaksFilterInd', 'cap');       
%       % 5x5 conditional sort on size and momentum using NYSE breaks
%       ind = makeBivSortInd(me, 5, R, 5, 'breaksFilterInd', 'NYSE', ...    
%                                         'sortType', 'unconditional');
%       % 5x5 conditional sort on size and momentum using NYSE breaks
%       ind = makeBivSortInd(me, 5, R, 5, 'NYSE', 'unconditional');   
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses makeUnivSortInd(), assignToPtf().
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Parse the inputs
expectedType = {'unconditional','conditional'};
p = inputParser;
validNum = @(x) isnumeric(x);
validNumSize = @(x) isempty(x) || ((islogical(x) || isnumeric(x)) && (isequal(size(var1),size(x)) || isequal(x,1)));
validSortType = @(x) isempty(x) || any(validatestring(x,expectedType));
addRequired(p, 'var1', validNum);
addRequired(p, 'ptfNumThresh1', validNum);
addRequired(p, 'var2', validNum);
addRequired(p, 'ptfNumThresh2', validNum);
addOptional(p, 'sortType', 'unconditional', validSortType);
addOptional(p, 'breaksFilterInd', 1, validNumSize);
addOptional(p, 'portfolioMassInd', 1, validNumSize);
parse(p, var1, ptfNumThresh1, var2, ptfNumThresh2, varargin{:});

% Assign the inputs
var1 = p.Results.var1;
ptfNumThresh1 = p.Results.ptfNumThresh1;
var2 = p.Results.var2;
ptfNumThresh2 = p.Results.ptfNumThresh2;
sortType = p.Results.sortType;
breaksFilterInd = p.Results.breaksFilterInd;
portfolioMassInd = p.Results.portfolioMassInd;

% Initialize the double sort index
ind = zeros(size(var1));

% sort based on the first variable
ind1 = makeUnivSortInd(var1, ptfNumThresh1, 'breaksFilterInd', breaksFilterInd, ...
                                            'portfolioMassInd', portfolioMassInd);

% Store the number of portfolios 
n1 = max(max(ind1));

% Check the double sort type
if strcmp(sortType,'unconditional')
    % If unconditional
    % Sort based on the secon variable
    ind2 = makeUnivSortInd(var2, ptfNumThresh2, 'breaksFilterInd', breaksFilterInd, ...
                                                'portfolioMassInd', portfolioMassInd);
    % Store the number of portfolios
    n2 = max(max(ind2));
    
    % Create the combined n1 x n2 portfolios
    for i = 1:n1   
        for j = 1:n2                             
            ind(ind1==i & ind2==j) = (i-1)*n2 + j;   % Give it a number, in the end, all will be from 1 to n1*n2
        end
    end
else 
    % If conditional 
    for i=1:n1
        % Sort within each of the portfolios sorted based on the first
        % variable
        temp = var2;
        temp(ind1~=i) = nan;
        tempInd = makeUnivSortInd(temp, ptfNumThresh2, 'breaksFilterInd', breaksFilterInd, ...
                                                       'portfolioMassInd', portfolioMassInd);
        n2 = max(max(tempInd));
        ind(ind1==i & tempInd>0) = tempInd(ind1==i & tempInd>0)+n2*(i-1);    
    end       
end