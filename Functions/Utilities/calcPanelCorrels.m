function [rhoS,rhoP]=calcPanelCorrels(var1,var2)
% PURPOSE: This function calculates Spearman rank and Pearson correlation
% coefficients between two variables stored matrices with dimensions equal
% to number of months by number of stocks
%------------------------------------------------------------------------------------------
% USAGE:   
% [rhoS,rhoP]=calcPanelCorrels(var1,var2)              % 4 required arguments.                                 
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -var1 - a matrix of a variable of interest                                  
%        -var2 - a matrix of a second variable of interest
%------------------------------------------------------------------------------------------
% Output:
%        -rhoS - Spearman correlation coefficient
%        -rhoP - Pearson correlation coefficient
%------------------------------------------------------------------------------------------
% Examples:
%
% [rhoS,rhoP]=calcPanelCorrels(REVT./AT,COGS./AT)  % Calculates the correlation between
%                                                     revenues and cost-of-goods-sold,
%                                                     where both variables  are scaled 
%                                                     by total assets
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

n=size(var1,1)*size(var1,2);

reshapedVars = [reshape(var1,n,1) reshape(var2,n,1)];
reshapedVars(isnan(sum(reshapedVars,2)),: )= [];
rhoP = corr(reshapedVars(:,1),reshapedVars(:,2));
rhoS = corr(reshapedVars(:,1),reshapedVars(:,2),'Type','Spearman');

