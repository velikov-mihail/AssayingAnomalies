function [GammaBeta,  Lambda] = runIPCAforMonth(chars, xret)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It estimates the latent factor realizations and mapping from
% characteristics using the Instrumented Principal Components from Kelly, 
% Pruitt, and Su (2019).The code here is based on the publicly-available
% code from Kelly, Pruitt, and Su (2019).
%------------------------------------------------------------------------------------------
% USAGE:   
% [GammaBeta,  Lambda] = runIPCAforMonth(chars, xret)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - chars - 3-d numeric array (nMonths x nStocks x nAnoms) 
%                        with filled-in anomaly signals
%        - xret - numeric matrix (nMonths x nStocks) with monthly returns
%------------------------------------------------------------------------------------------
% Output:
%        - GammaBeta - mapping matrix from characteristics to factors
%        - Lambda - latent factor return
%------------------------------------------------------------------------------------------
% Examples:
%
% [GammaBeta,  Lambda] = runIPCAforMonth(chars, xret);
%------------------------------------------------------------------------------------------
% Dependencies:
%       Used by makeIPCARes
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Kelly, B., Pruitt, S., and Y. Su, 2019, Characteristics are
%  covariances: A unified model of risk and return, Journal of Financial
%  Economics, 134 (3): 501-524
%  2. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Permute the characteristics & filter to stock/months with observations
% for all characteristics
chars = permute(chars, [2 1 3]);
LOC = ~isnan(chars);
LOC = all(LOC, 3) & ~isnan(xret);

% Store a few constants
[~, nMonths, nAnoms] = size(chars);

% Add a constant
nAnoms = nAnoms + 1;
chars(:, :, nAnoms)  = 1;

% Store the number of stocks
Nts = sum(LOC);

% Construct X, W, X
chars = permute(chars, [1 3 2]); % chars is now NxLxT
Z     = chars;
W  = nan(nAnoms, nAnoms, nMonths);
X  = nan(nAnoms, nMonths);
for t = 1:nMonths 
    
    % W = Z'Z
    W(:,:,t) = (1/Nts(t)) * Z(LOC(:,t),:,t)' * Z(LOC(:,t),:,t); 
    
    % X = Z'r
    X(:,t)   = (1/Nts(t)) * Z(LOC(:,t),:,t)' * xret(LOC(:,t),t); 
end

K = 5;
als_opt.MaxIterations = 10000;
als_opt.Tolerance     = 1e-6;
Nts = sum(LOC);


% Initial guess for GammaBeta & the factor(s)    
[GammaBeta_initial, s, v] = svds(X, K);
GB_Old      = GammaBeta_initial;
F_Old       = s*v'; %ones(K,T);%

% Iterate until you reach tolerance or max iterations
tol         = 1;
iter        = 0;
while iter <= als_opt.MaxIterations && tol > als_opt.Tolerance
    [GB_New, F_New] = num_IPCA_estimate_ALS(GB_Old, W, X, Nts);
    tol     = max([ abs(GB_New(:) - GB_Old(:)); abs(F_New(:)-F_Old(:)) ]);
    F_Old   = F_New;
    GB_Old  = GB_New;
    iter    = iter+1;
end

% Store the output
GammaBeta = GB_New;
Lambda = mean(F_New,2);        

