function tcosts = fillMissingTcosts(tcosts_raw)
% PURPOSE: This function fills in missing trading costs observations based
% on the shortest Euclidean distance in market capitalization and
% idiosyncratic volatility rank space following Novy-Marx and Velikov
% (2016)
%------------------------------------------------------------------------------------------
% USAGE:   
% tcosts = fillMissingTcosts(tcosts_raw)       % Creates the trading costs measures
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -tcosts_raw - a matrix of raw trading costs estimates 
%------------------------------------------------------------------------------------------
% Output:
%        -tcosts - a matrix of filled-in trading costs estimates
%------------------------------------------------------------------------------------------
% Examples:
%
% tcosts = fillMissingTcosts(tcosts_raw)             
%------------------------------------------------------------------------------------------
% Dependencies:
%       Used by makeTCosts(), 
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2016, A taxonomy of anomalies and their
%  trading costs, Review of Financial Studies, 29 (1): 104-147
%  2. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Assign the raw tcosts matrix to a new matrix that we will fill in 
tcosts = tcosts_raw;

% Load size and idiosyncratic volatility
load me
load IffVOL3 

% Create the rank matrices 
rme = tiedrank(me')';
rIVOL = tiedrank(IffVOL3')';

% First we'll assign trading costs based on the best match on me & IVOL
% Store the indices
idxToMatch = isfinite(me + IffVOL3 + tcosts_raw);
idxToFill = isfinite(me + IffVOL3) & isnan(tcosts);

% Store the number of months
nMonths = size(me, 1);

for i = 1:nMonths
    
    % Figure out for which stocks we need to fill in tcosts for this month
    stocksToFill = find(idxToFill(i, :));
    nStocksToFill = length(stocksToFill);
    
    % Loop through them
    for k = 1:nStocksToFill
        j = stocksToFill(k);
        
        % Store the index from which we are matching from
        ind = idxToMatch(i,:);
        
        % Calculate the distance for stocks with me & IVOL observations in
        % this month
        distance = sqrt( ( rme(i,ind)   - rme(i,j)   ) .^2 + ...
                         ( rIVOL(i,ind) - rIVOL(i,j) ) .^2 );
        
        % Find the minimum distance and assign the match
        minDist = min(distance);
        match = find(distance == minDist);
                        
        % Assign it if not empty
        if ~isempty(match)
            tcostsToMatchFrom = tcosts_raw(i, ind);
            tcosts(i,j) = tcostsToMatchFrom(match(1));
        end
    end
end

% First we'll assign trading costs based on the best match on me only
% Store the indices
idxToMatch = isfinite(me + tcosts_raw);
idxToFill = isfinite(me) & isnan(tcosts);

% Store the number of months
nMonths = size(me, 1);

for i = 1:nMonths
    
    % Figure out for which stocks we need to fill in tcosts for this month
    stocksToFill = find(idxToFill(i, :));
    nStocksToFill = length(stocksToFill);
    
    % Loop through them
    for k = 1:nStocksToFill
        j = stocksToFill(k);
        
        % Store the index from which we are matching from
        ind = idxToMatch(i,:);
        
        % Calculate the distance for stocks with me 
        distance = abs( rme(i,ind) - rme(i,j) );
        
        % Find the minimum distance and assign the match
        minDist = min(distance);
        match = find(distance == minDist);
                        
        % Assign it if not empty
        if ~isempty(match)
            tcostsToMatchFrom = tcosts_raw(i, ind);
            tcosts(i,j) = tcostsToMatchFrom(match(1));
        end
    end
end
