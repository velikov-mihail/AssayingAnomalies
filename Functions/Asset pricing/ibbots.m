function [cumRets] = ibbots(rets,dates,varargin)
% PURPOSE: This function calculates and plots the cumulative returns for
% portfolio series 
%------------------------------------------------------------------------------------------
% USAGE:   
% [cumRets] = ibbots(rets,dates);                   % 2 required arguments.                                 
% [cumRets] = ibbots(rets,dates,Name,Value);        % Allows you to specify optional inputs
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -rets - a matrix of stock returns                                  
%        -dates - a vector of dates in YYYYMM or YYYYMMDD format                                  
% Optional Name-Value Pair Arguments:
%        -'timePeriod' - a scalar or two-by-one vector of dates in YYYYMM or YYYYMMDD 
%                        format indicating sample start or sample range (default is first 
%                        element in dates)
%        -'linPlotInd' - a flag indicating whether to plot the cumulative
%                        returns on a linear or log (default) scale
%        -'legendLabels' - a cell array of legend labels
%------------------------------------------------------------------------------------------
% Output:
%        -cumRets - a matrix with the cumulative returns used in the plot 
%------------------------------------------------------------------------------------------
% Examples:
%
% [cumRets] = ibbots(mkt,dates);                       % Plot the market returns                                
% [cumRets] = ibbots(dmkt,ddates,19630701);            % Plot the market returns post 196307 
%                                                        using the daily data
% [cumRets] = ibbots(mkt,dates,'lindPlotInd',1);       % Plot the market returns on linear 
%                                                        scale                             
% [cumRets] = ibbots([mkt smb],dates,...               % Plot the market and SMB returns 
%                    'legendLabels',{'MKT','SMB'});      and include a legend
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses calcPtfRets()
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

p=inputParser;
validNum=@(x) isnumeric(x);
addRequired(p,'rets',validNum);
addRequired(p,'dates',validNum);
addOptional(p,'timePeriod',[dates(1) dates(end)],validNum);
addOptional(p,'linPlotInd',0,validNum);
addOptional(p,'legendLabels',{''});
parse(p,rets,dates,varargin{:});

% Check if user entered a subsample
if ~isequal(p.Results.timePeriod, [dates(1) dates(end)])
    s = find(dates>=p.Results.timePeriod(1),1,'first');
    if length(p.Results.timePeriod)==2
        e = find(dates<=p.Results.timePeriod(2),1,'last');
    else
        e = length(dates);
    end
    rets = rets(s:e,:);
    dates = dates(s:e);
end         

% Check if daily or monthly returns
if length(num2str(dates(1))) == 8
    x = floor(dates/10000) + (floor(mod(dates,10000)/100)-1)/12 + mod(dates,100)/(12*30);
else
    x = floor(dates/100) + mod(dates,100)/12;
end


x = [2*x(1)-x(2); x];

rets(isnan(rets)) = 0;
y = cumprod(1+[zeros(1,size(rets,2)); rets]);


if p.Results.linPlotInd == 1
    plot(repmat(x,1,size(y,2)),(y-1),'LineWidth',2.5)
    xlim([x(1) x(end)])
    ylim([(0.9*min(min(y))-1) (1.1*max(max(y))-1)])
    title(['Cumulative gains (%)'],'FontName','Times New Roman','FontSize',12)
else
    semilogy(repmat(x,1,size(y,2)),y,'LineWidth',2.5)
    xlim([x(1) x(end)])
    ylim([0.8*min(min(y)) 1.4*max(max(y))])
    title(['Performance of $1 (log scale)'],'FontName','Times New Roman','FontSize',12)
    set(gca,'YTick',10.^[0:8])
    set(gca,'YTickLabel',{'$1';'$10';'$100';'$1,000';'$10,000';'$100,000';'$1,000,000';'$100,000,000'})
end

set(gca,'FontSize',12)
set(gca,'FontName','Times New Roman')

if ~isempty(p.Results.legendLabels{1})
    if size(rets,2) ~= length(p.Results.legendLabels)
        error('Wrong number of legend labels.');
    end
    legend(p.Results.legendLabels,'Location','Northwest');
end


cumRets = y;
