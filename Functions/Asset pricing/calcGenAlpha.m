function [alpha_res, w_x_y, w_x] = calcGenAlpha(anomRet, anomTcosts, factorRets, factorTcosts, printRes)
% PURPOSE: Calculates the generalized alpha of an anomaly relative to a set
% of factors. 
%------------------------------------------------------------------------------------------
% USAGE: 
%       [alpha_res] = calcGenAlpha(anomRet, anomTcosts,  ...
%                                  factorRets, factorTcosts, ...
%                                  printRes);                   
%------------------------------------------------------------------------------------------
% Required Inputs:
%       -anomRet - vector of gross anomaly portfolio returns 
%       -anomTcosts - vector of trading costs for anomaly portfolio
%       -factorRets - matrix of gross factor portfolios returns 
%       -factorTcosts - matrix of trading costs for factor portfolios 
%       -printRes - an indicator of whether to print the results
%------------------------------------------------------------------------------------------
% Output:
%       -alpha_res - a structure with OLS results of regressing the MVE of
%       (x, y), scaled by the weight of y in (x, y) on the MVE of (x)
%       -w_x_y - weights in the MVE of (x, y)
%       -w_x - weights in the MVE of (x)
%------------------------------------------------------------------------------------------
% Example (Momentum four-factor generalized alpha from Novy-Marx and Velikov, RFS, 2016): 
%           clear
%           clc
%           
%           % Load variables    
%           load ff
%           load ret
%           load dates
%           load me
%           load tcosts
%           load R
%           load ff_tc         
%           load NYSE
%           
%           % Run a momentum decile sort with NYSE breakpoints
%           indR10 = makeUnivSortInd(R, 10, NYSE);
%           Res = runUnivSort(ret, indR10, dates, me, 'tcosts', tcosts, ...
%                                                     'timePeriod', [196301 200912], ...
%                                                     'printResults', 0, ...
%                                                     'plotFigure',0);              
%            
%           % Calculate the generazlied four-factor alpha for that period
%           sizeRet = Res.pret(:, end); 
%           sizeTcosts = Res.tcostsTS;
%           factorRets = [mkt smb hml umd];
%           factorTcosts = [zeros(size(mkt)) smb_tc hml_tc umd_tc];
%           ind=find(dates>=196301 & dates<=200912);
%           [alpha_res, wxy, wx] = calcGenAlpha(sizeRet, sizeTcosts, factorRets(ind,:), factorTcosts(ind,:), 1);                      
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses calcNetMve(), nanols().
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2016, A Taxonomy of Anomalies and Their
%  Trading Costs, Review of Financial Studies, 29 (1): 104-147
%  2. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.


% Check if they are same size
if size(anomTcosts,1)~=size(anomRet,1) || size(anomTcosts,1)~=size(factorRets,1) || size(factorTcosts,1)~=size(factorRets,1)
    error('Anomaly return and factors return series are different lenghts.');
end

grossAnomFactors = [factorRets anomRet];
tcostsAnomFactors = [factorTcosts anomTcosts];

[w_x_y, ~] = calcNetMve(grossAnomFactors - tcostsAnomFactors, ...
                       -grossAnomFactors - tcostsAnomFactors);

[w_x, ~] = calcNetMve(factorRets - factorTcosts, ...
                     -factorRets - factorTcosts);
                   
if w_x_y(end) ~= 0    
    y = (grossAnomFactors * w_x_y - tcostsAnomFactors * abs(w_x_y)) / abs(w_x_y(end));
    x = factorRets * w_x - factorTcosts * abs(w_x);
    alpha_res = nanols(100*y,[ones(size(y)) x]);
else
    alpha_res =  ols(ones(size(anomRet)), nan(size(anomRet)));
end

if printRes~=0 
    prt(alpha_res)
end
