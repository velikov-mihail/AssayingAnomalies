function [out]=histomap(long,lat,variable,varargin)
% PURPOSE: This function links a map and an histogram
%------------------------------------------------------------------------
% USAGE: out=histomap(long,lat,variable,nbcl,carte,label,symbol)
%   where : lat = n x 1 vector of coordinates on the second axis
%           long = n x 1 vector of coordinates on the first axis
%           variable = n x 1 vector of the variable to study
%           nbcl = number(integer) of classes of the histogram. '' is for Default setting. Default is 10
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on the map by clicking with the left mouse button
%         Select bars on the histogram by clicking with the left mouse button
%         You can select points inside a polygon on the map: - right click to set the first point of the polygon
%                                                            - left click to set the other points
%                                                            - right click to close the polygon
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses selectmap.m, selectstat.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr





close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
vectx=[];
vecty=[];
name=inputname(3);
symbol=0;
%creation d'un menu pour sauver
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save histfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        nbc=varargin{1};
    else 
        nbc=10;
    end;
    if  t>=2 & ~isempty(varargin{2})
        carte=varargin{2};
        c=1;
    else 
        c=0;
    end;
    if  t>=3 & ~isempty(varargin{3})
        label=varargin{3};
        l=1;
    else 
        l=0;
    end;
    if t==4 & ~isempty(varargin{4})
        symbol=varargin{4};
    end;
else
    nbc=10;
    c=0;
    l=0;
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%

% Trace the histogram
Axis2=subplot(1,2,2);
edge=[min(variable):(max(variable)-min(variable))/nbc:max(variable)-(max(variable)-min(variable))/nbc];
edge2=[edge,inf];
N=histc(variable,edge2);
N=N(1:end-1);
bar(edge,N,'histc','b');
xlabel(name);
axis manual;
subplot(Axis1);
axis manual;
Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Main loop
maptest=0;
histotest=0;
BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    bar(edge,N,'histc','b');
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    if ~isempty(Iselect)
        if maptest==1
            N2=histc(variable(Iselect),edge2);
            N2=N2(1:end-1);
            bar(edge,N2,'histc','r');
        elseif histotest==1
            N2=histc(variable(Iselect),edge2);
            N2=N2(1:end-1);
            bar(edge,N2,'histc','m');
        end;
    end;
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if ~isempty(Iselect)
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'b*');  
            else
                plot(long(Iselect),lat(Iselect),'r.');      
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif histotest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'bo');  
            else
                plot(long(Iselect),lat(Iselect),'m.');      
            end;
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0     
            maptest=1;
            histotest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');
        %%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%
    % histogram selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if histotest==0
            histotest=1;
            maptest=0;
            obs=zeros(size(long,1),1);
        end;
        % bar selection
        if BUTTON~=3 & BUTTON~=2 
            obs=selectstat('histo',obs,variable,edge2,N,x,y);
        end;
        %%%%%%%%%%%%%%%
    end;
    %%%%%%%%%%%%%%%%%%
end;
out=obs;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%