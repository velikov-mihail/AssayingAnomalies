function [weights, SR] = calcNetMve(rets, rets_s)
% PURPOSE: calculates optimal weights and Sharpe ratio from a set of net 
% asset long and short returns
%---------------------------------------------------
% USAGE: [weights, SR] = calcMve(rets, rets_s)     
%---------------------------------------------------
% Inputs
%        -rets - matrix with asset returns assuming a long position
%        (nTimePeriods x nAssets)
%        -rets_s - matrix with asset returns assuming a short position
%        (nTimePeriods x nAssets)
% Outputs
%        -weights - vector of weights on each asset in the mean-variance
%                   efficient portfolio (1 x nAssets)
%        -SR - scalar indicating the Sharpe ratio of the mean-variance
%                   efficient portfolio (1 x 1)
% This function works by searching through all combinations of factor
% positions being long, short, or not held. That, we calculate the Sharpe
% ratios for all 3^(nFactor-1) combinations of factor directional
% positions. We use the highest Sharpe ratio that has positive weights on
% the signed factors. The only exception is that we assume that we assume
% no trading costs for the market, so any position (long, short, not held)
% is fine. 

% Store a few constants
nFactors = size(rets,2);
nCombs = 3^(nFactors-1);

% Initialize the position index. This will tell us whether a factor is
% long, short, or not held in a given combination
posIndex = nan(nCombs, nFactors);

% We assume market is costless to trade, so always enters the MVE
% calculation as long
posIndex(:,1) = [ones(nCombs,1)];

% Find the combinations (long, short, not held) for the other factors
xt = [nCombs:-1:1]'-1; 
for i=2:(nFactors)
    ttemp = mod(xt,3);
    xt = (xt-ttemp)/3;
    posIndex(:,i) = ttemp;
end

% Start with a SR & weights equal to zero
SR = 0;
weights = zeros(nFactors, 1);

% Check if we have more than one factor
if nFactors > 1

    % Calculate a starting Sharpe ratio using the optimal tangency 
    % portfolio weights
    [startWeights, startSR] = calcMve(rets);

    % Check if all non-market weights are positive & that we have a 
    % positive starting Sharpe ratio
    nonMktWeights = startWeights(2:end);
    nNonMktFactors = nFactors - 1;
        
    if sum(nonMktWeights>0) == nNonMktFactors && startSR > SR
        % If so, we are done
        weights = startWeights;
        SR = startSR;
    else

        % If not, we have to loop through the combinations
        for i = 1:nCombs
            % Store the returns for this combination. start with the long
            % position returns
            thisCombRets = rets;

            % Find the short positions for this combination & replace them
            indShort = posIndex(i,:) == 2;
            thisCombRets(:, indShort) = rets_s(:,indShort); 

            % Find the not-held positions for this combination & remove them
            thisCombPosIndex = posIndex(i,:);
            indNotHeld = thisCombPosIndex == 0;
            thisCombRets(:, indNotHeld) = []; 

            % Calculate the number of factors left
            nFactorsLeft = sum(~indNotHeld);                

            % Store a position index by excluding not held assets
            thisPosIndex = thisCombPosIndex(~indNotHeld);

            % Calculate the weights & Sharpe ratio for this combination
            [thisCombWghts, thisCombSR] =  calcMve(thisCombRets);

            % Check if the weights on non-market factors are all positive
            if sum(thisCombWghts(2:end)>0) == (nFactorsLeft-1)

                % Check if this Sharpe ratio is better
                if thisCombSR > SR
                    % If so, assign the Sharpe ratio
                    SR = thisCombSR;

                    % And the weights
                    tempWghts = zeros(1,nFactors);
                    tempWghts(thisCombPosIndex==1) = thisCombWghts(thisPosIndex == 1)';
                    tempWghts(thisCombPosIndex==2) = -thisCombWghts(thisPosIndex == 2)';
                    weights = tempWghts';
                end
            end
        end
    end
else 
    % We have only 1 factor. Check long & short Sharpe ratios
    longMeanSharpe = mean(rets)/std(rets);
    shortMeanSharpe = mean(rets_s)/std(rets_s);
    
    % If long is higher & positive, we go long
    if longMeanSharpe > shortMeanSharpe && longMeanSharpe > 0
        weights = 1;
        SR = longMeanSharpe;
    % If short is higher & positive, we go short
    elseif shortMeanSharpe > longMeanSharpe && shortMeanSharpe > 0
        weights = -1;
        SR = shortMeanSharpe;      
    end
end
