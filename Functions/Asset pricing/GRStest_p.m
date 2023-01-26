function [pvals, Fstats, dfs] = GRStest_p(results)
% PURPOSE: This function calculates a Gibbons, Ross, and Shanken (1989) 
% test statistic and its associated p-value
%------------------------------------------------------------------------------------------
% USAGE:   
% [pvals, Fstats, dfs] = GRStest_p(results)                                        
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - results - a results structure that is output by runUnivSort()
%------------------------------------------------------------------------------------------
% Output:
%        - pvals - p-value for the F-statistic
%        - Fstats - GRS F-statistics
%        - dfs - degrees of freedom 
%------------------------------------------------------------------------------------------
% Examples:
%
% [pvals, Fstats, dfs] = GRStest_p(results);                                     
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses output from runUnivSort(); Used by runBivSort();
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Initialize a few variables
pvals = ones(2,1);
df = zeros(2, 2);
stats = ones(2,1);

% Store a few variables
nPtfs = size(results.pret,2);
nMonths = sum(isfinite(results.pret(:,1)));
nFactors = results.nFactors;

% Calculate the GRS stat for the full model %
% Get the degrees of freedom
df(1,:) = [nPtfs, nMonths - nPtfs - nFactors];

indFinite = isfinite(sum(results.pret,2)) & isfinite(sum([results.factorLoadings.factor],2)); 

% Calculate the numerator
numer = results.alpha(1:nPtfs)' * cov(results.resid(indFinite,1:nPtfs))^(-1) * results.alpha(1:nPtfs);
numer = numer/100^2; %correct for percentage return multiplication

% Calculate the denominator
f_mat = [];
for i = 1:nFactors
    f_mat = [f_mat, results.factorLoadings(i).factor(indFinite)] ;
end
Ef = mean(f_mat, 1, 'omitnan')';
denom = 1 + Ef'*cov(f_mat)^(-1)*Ef;

% The statistic
stats(1) = df(1,2)/df(1,1) * numer/denom;

pvals(1) = 1 - fcdf(stats(1), df(1,1), df(1,2));


% Calculate the GRS stat for the reduced model %
b = [results.factorLoadings.b]';
b = b(:,1:nPtfs);
x = [results.factorLoadings.factor];
x = x(indFinite, :);
a = repmat(results.alpha(1:nPtfs)', sum(indFinite), 1)/100;
resid = results.resid(indFinite,1:nPtfs);
resxret = x*b + a + resid;

% Calculate the numerator
numer = results.xret(1:nPtfs)'*cov(resxret)^(-1)*results.xret(1:nPtfs);
numer = numer/100^2; %correct for percentage return multiplication
denom = 1;
df(2,:) = [nPtfs, nMonths - nPtfs];

% The statistic
stats(2) = df(2,2)/df(2,1) * numer/denom;
pvals(2) = 1 - fcdf(stats(2), df(2,1), df(2,2));

if nargout == 3
    Fstats = stats;
    dfs = df;
end
